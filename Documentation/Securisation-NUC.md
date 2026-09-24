# Compte rendu de séance : sécurisation du NUC

|  |  |
| --- | --- |
| Date | 16 septembre 2026 |
| Partie | Cybersécurité |
| Machine | NUC de l'installation (Intel NUC8i5BEH) |
| Objectif | Configurer le pare-feu Windows, mesurer ce qui sort de la machine, verrouiller le démarrage |

## Ce qui a été fait

1.  Activation de la journalisation du pare-feu Windows
    
2.  Inventaire des connexions sortantes
    
3.  Test du blocage de tout le trafic sortant pendant 13 minutes, puis analyse du journal
    
4.  Remise du pare-feu en mode normal
    
5.  Désactivation du démarrage sur USB et Thunderbolt
    
6.  Activation de Secure Boot
    
7.  Mise en place d'un mot de passe sur l'UEFI
    

## 1\. Pare-feu Windows

Un pare-feu décide de ce qui a le droit de passer sur le réseau. Par défaut, celui de Windows bloque ce qui entre mais laisse sortir tout ce que la machine veut envoyer. Le but est d'inverser ça pour le trafic sortant : que la machine ne parle qu'à l'IA en ligne.

### Profils réseau

Avant de toucher aux règles, il faut savoir où elles s'appliquent. Windows a trois jeux de règles selon le type de réseau : Domain (réseau d'entreprise), Private (réseau de confiance) et Public (lieu public). C'est Windows qui choisit selon le réseau branché, donc tout a été configuré sur les trois.

### Journalisation

Par défaut, le pare-feu bloque sans rien noter : impossible ensuite de savoir ce qu'il a arrêté. On a donc activé la journalisation, qui écrit chaque paquet bloqué dans un fichier avec l'heure, la destination et le protocole.

Réglage fait dans Windows Defender Firewall Properties → Logging → Customize, sur les trois profils :

| Paramètre | Valeur |
| --- | --- |
| Enregistrer les paquets bloqués | Oui |
| Taille maximale | 16 384 Ko |
| Fichier | C:\Windows\System32\LogFiles\Firewall\pfirewall.log |

### Inventaire

Avant de bloquer quoi que ce soit, on a regardé ce qui sortait déjà de la machine, et quel programme en était responsable :

```powershell
# Connexions ouvertes : destination, port, numéro du programme
Get-NetTCPConnection -State Established | Select-Object RemoteAddress, RemotePort, OwningProcess
 
# Nom du programme qui correspond à chaque numéro
Get-Process | Select-Object Id, ProcessName, Path
```

  

| Programme | Connexions | Vers |
| --- | --- | --- |
| Firefox | environ 45 | Google, Akamai, Fastly |
| Avast | environ 20 | Google Cloud, Akamai |
| Microsoft Edge | 2 | Microsoft |
| Services Windows | 3 | Microsoft |

Toutes passent par le port 443, celui du HTTPS (trafic web chiffré). L'application du projet n'est pas encore installée, elle n'apparaît donc pas.

### Test de blocage

Cet inventaire ne montre que les connexions ouvertes à un instant donné. Pour voir tout ce que la machine essaie d'envoyer sur une durée, on a bloqué tout le trafic sortant :

```powershell
Set-NetFirewallProfile -Profile Domain,Public,Private -DefaultOutboundAction Block
```

  

Plus rien ne sort sauf ce qui est autorisé, et chaque tentative est enregistrée dans le journal. La machine est restée 13 minutes sans qu'on y touche.

### Résultats

1 064 paquets sortants bloqués en 13 minutes, soit environ 80 par minute, alors que l'application n'est même pas installée. Premier blocage à 14:30:24, au moment où la règle a été appliquée.

| Destination | Paquets | Propriétaire |
| --- | --- | --- |
| 142.251.142.67 | 463 | Google |
| 2.22.6.22 | 96 | Akamai |
| 72.145.35.144 | 59 | Microsoft |
| 142.251.209.74 | 41 | Google |
| 98.66.133.184 et .186 | 42 | Microsoft |
| 8.8.8.8, 8.8.4.4, 1.1.1.1 | 30 chacun | Serveurs DNS publics de Google et Cloudflare |
| 239.255.255.250 | 30 | Réseau local |

Le journal ne donne que des adresses IP. Pour savoir à qui elles appartiennent, on a d'abord demandé son nom à chaque adresse avec Resolve-DnsName. Pour 2.22.6.22, la réponse contient akamaitechnologies.com : l'adresse appartient à Akamai, une entreprise qui garde des copies de sites et de fichiers sur des serveurs répartis dans le monde, et par laquelle beaucoup de logiciels font passer leurs mises à jour. Mais la plupart des adresses ne répondent pas à cette question. Pour celles-là, on a cherché à qui appartient le bloc d'adresses dont elles font partie.

Une fois les destinations identifiées, le journal montre quatre comportements.

Le premier saute aux yeux : une seule adresse Google représente 44 % des blocages.

Le deuxième se repère à sa régularité. Toutes les 30 à 90 secondes, un logiciel envoie cinq ping vers 8.8.8.8, 8.8.4.4 et 1.1.1.1. C'est un test de connexion : il vérifie en boucle si Internet répond.

Le troisième ne va pas vers Internet mais vers le réseau local. La machine envoie du LLMNR (port 5355) et du SSDP (port 1900), deux protocoles qui cherchent les autres appareils du réseau. Au passage, elle leur donne son nom.

Le dernier concerne Avast. Quand le port 443 est bloqué, il ne s'arrête pas : il essaie de sortir par le port 7500, qu'il utilise pour ses notifications d'après sa documentation.

Ces chiffres sont à prendre avec une réserve : Firefox était ouvert, une partie des blocages vient donc de la navigation.

Le fichier journal est gardé comme preuve.

### Remise en état

```powershell
Set-NetFirewallProfile -Profile Domain,Public,Private -DefaultOutboundAction Allow
```


Le blocage empêche aussi le groupe d'utiliser Internet sur la machine. Il a donc été retiré, et sera réactivé quand les règles de l'application seront écrites.

## 2\. Verrouillage du démarrage
 
### BIOS et UEFI
 
Le pare-feu protège Windows, mais seulement quand c'est Windows qui tourne. Tout dépend donc de ce qui se passe avant, au démarrage.
 
Quand on allume la machine, un programme stocké sur la carte mère vérifie le matériel puis lance le système. Ce programme s'appelait autrefois le BIOS. Il a été remplacé par l'UEFI, plus récent, mais le mot « BIOS » est resté dans l'usage courant, et Intel appelle même le sien « Visual BIOS ». Sur le NUC, c'est bien un UEFI.
 
C'est l'UEFI qui choisit quel système démarrer. Si quelqu'un démarre la machine sur une clé USB avec un autre système, Windows ne tourne pas, nos réglages ne s'appliquent pas, et le disque est lisible par n'importe qui. C'est ce qui a été corrigé pendant cette séance. On accède à l'UEFI avec F2 au démarrage.