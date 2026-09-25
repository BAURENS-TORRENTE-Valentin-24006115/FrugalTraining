# 1\. Contexte et périmètre

## 1.1 Présentation de Frugal Training

Frugal Training est un projet réalisé pour le compte d'un client extérieur M. Beyrouthy dans le cadre d'une exposition artistique consacrée à “l'art d'ordinateur”.

Le projet consiste à concevoir un dispositif mettant en scène une intelligence artificielle réentraînée à partir d'un jeu de données représentant une vision dite frugaliste. L'objectif est de permettre à cette intelligence artificielle de produire des réponses cohérentes avec cette vision et de les confronter à celles produites par différentes intelligences artificielles publiques.

Le fonctionnement général repose sur plusieurs étapes. L'IA réentraînée constitue le point central du dispositif. Elle envoie un questionnaire qui est ensuite soumis à plusieurs IA publiques, telles que Mistral, Gemini ou d'autres modèles similaires. Les réponses obtenues sont ensuite récupérées et analysées afin de produire un résultat permettant de comparer les différentes visions exprimées.

À partir de ces résultats, l'IA réentraînée fournit une réponse ou une interprétation finale correspondant à la logique frugaliste du projet.

Le dispositif peut également intégrer une interface graphique permettant de représenter visuellement l'IA qui répond, notamment au moyen d'une bulle qui s'étend progressivement lors de la génération de la réponse. Cet élément est optionnel et dépend des choix réalisés concernant l'interface finale de l'installation.

Le projet prévoit également l'utilisation de deux bases de données distinctes :

-   une base de données Frugaliste, contenant les données associées à la vision frugaliste ;
    
-   une base de données Technosolutioniste, permettant de représenter et de conserver les données associées à une vision technosolutionniste.
    

L'ensemble forme ainsi un dispositif à la fois informatique, expérimental et artistique, dans lequel l'intelligence artificielle constitue un élément central de l'expérience proposée au public.

## 1.2 Contexte de la SAE

Ce projet est réalisé dans le cadre de la SAE S6.01 et constitue une reprise et une évolution du projet réalisé en 2025.

Dans cette nouvelle phase, une attention particulière est portée à la sécurité de l'infrastructure nécessaire au fonctionnement de l'installation. Le projet doit notamment pouvoir fonctionner sur une infrastructure matérielle limitée, tout en assurant un niveau de sécurité suffisant pour une utilisation dans le contexte d'une exposition.

Le parcours Réseaux & Cybersécurité conduit notamment à étudier la sécurisation du matériel utilisé, des communications réseau, des services hébergés localement, des bases de données ainsi que des échanges avec les services d'intelligence artificielle externes.

Le présent dossier a donc pour objectif de formaliser l'analyse de sécurité du dispositif et de servir de support aux choix techniques réalisés au cours du développement.

## 1.3 Objectifs du dossier de sécurité

L'objectif de ce dossier est d'identifier les principaux risques pouvant affecter le fonctionnement ou les données de Frugal Training et de définir les mesures permettant de les limiter.

L'étude porte notamment sur :

-   la sécurité du NUC utilisé pour l'installation ;
    
-   les communications entre les différents composants du dispositif ;
    
-   les échanges avec les IA publiques utilisées par le projet ;
    
-   la protection des clés d'API nécessaires à l'utilisation de ces services ;
    
-   la protection des deux bases de données ;
    
-   la protection des données utilisées pour le réentraînement de l'IA ;
    
-   la gestion des utilisateurs et des droits d'accès ;
    
-   la protection contre les accès physiques non autorisés ;
    
-   les sauvegardes et la restauration des données ;
    
-   les risques liés aux entrées transmises aux modèles d'intelligence artificielle, notamment les attaques par injection de prompt ;
    
-   les mécanismes permettant de tester et de vérifier les mesures de sécurité mises en place.
    

Le but n'est pas d'ajouter systématiquement des mécanismes de sécurité, mais de déterminer quelles protections sont réellement nécessaires au regard des risques, du fonctionnement de l'installation et des contraintes matérielles du projet.

## 1.4 Périmètre de l'étude

Le périmètre de l'étude comprend les composants informatiques directement nécessaires au fonctionnement de l'installation.

Sont notamment concernés :

-   le NUC et son système d'exploitation ;
    
-   les applications et services exécutés sur le NUC ;
    
-   l'architecture réseau de l'installation ;
    
-   la passerelle réseau et les éventuels mécanismes de filtrage ;
    
-   les deux bases de données Frugaliste et Technosolutioniste ;
    
-   le jeu de données utilisé pour le réentraînement de l'IA ;
    
-   le modèle d'IA réentraîné ;
    
-   les communications entre l'IA réentraînée et les IA publiques ;
    
-   les clés d'API et autres secrets nécessaires à ces communications ;
    
-   l'interface utilisée par le public ou par l'installation ;
    
-   les mécanismes de sauvegarde et de restauration ;
    
-   les journaux et éventuelles traces nécessaires au suivi du fonctionnement ;
    
-   les tests permettant de vérifier la sécurité du dispositif.
    

Les différentes architectures techniques envisagées, notamment l'utilisation d'une passerelle, d'un pare-feu et éventuellement de conteneurs Docker, seront étudiées avant de faire l'objet d'un choix définitif.

## 1.5 Éléments hors périmètre

La sécurité interne des services d'intelligence artificielle publics utilisés par le projet n'est pas directement contrôlable par l'équipe. Les fournisseurs de ces services restent responsables de leur propre infrastructure.

L'étude porte donc principalement sur la manière dont Frugal Training communique avec ces services, sur les données qui leur sont transmises et sur la protection des informations permettant d'y accéder.

De la même manière, les aspects purement artistiques ou graphiques de l'installation ne constituent pas le cœur de ce dossier de sécurité. Ils peuvent toutefois être pris en compte lorsqu'ils ont une incidence sur la sécurité ou le fonctionnement de l'infrastructure informatique.


# 2\. Savoir ce qu'on protège

Avant de choisir des protections, il faut lister ce qui a de la valeur et ce qui peut mal tourner. Sinon on pourrait se retrouver à oublier des choses à protéger.

## 2.1 Les biens

| Bien | Risque |
| --- | --- |
| Les documents nourrissant l'IA | L'IA change de discours sans qu'on comprenne pourquoi |
| Le questionnaire et son barème | Les scores affichés sont faux |
| L'historique des sessions | On perd les résultats de l'exposition |
| Personas (prompts système) | L'IA joue un autre personnage que prévu |
| Les modèles téléchargés | Plusieurs Go à retélécharger en plein festival |
| Secrets (clés d'API, mots de passe) | Quelqu'un d'autre s'en sert, le quota s'épuise et l'IA ne répond plus |
| La machine allumée | L'œuvre s'arrête en pleine exposition |

Rien là-dedans n'est confidentiel, sauf les secrets. Les documents viennent d'internet, les scores sont faits pour être affichés à l'écran, et le public ne laisse aucune donnée personnelle.

Ce qui compte ici, c'est l'exactitude des données et que la machine tourne.

## 2.2 Ce qui sort de la machine

L'installation fait dialoguer une IA sur la machine et une IA en ligne. À chaque question posée, quelque chose part vers l'extérieur.

Ce que le programme envoie exprès : les questions du questionnaire, les messages écrits par l'IA locale, et les informations techniques de la requête.

Ce qui revient : les réponses de l'IA en ligne.

Ce trafic est prévu et connu. Mais une machine ne se limite pas à ce qu'on lui a demandé de faire : Windows vérifie ses mises à jour et transmet des données de diagnostic, les logiciels installés contactent leurs propres serveurs, et certains services se signalent d'eux-mêmes aux autres appareils du réseau.

Tout cela part vers des destinations que personne dans le groupe n'a choisies, et en dit beaucoup sur la machine : nom de l'appareil, version du système, versions des logiciels installés. Les failles connues de ces versions sont répertoriées publiquement, avec souvent la façon de les exploiter. Une machine qui annonce sa version annonce donc aussi ce qui marche contre elle.

C'est l'objectif du pare-feu : autoriser les appels à l'IA en ligne, bloquer tout le reste. Les blocages sont enregistrés, ce qui permet de vérifier ce qui a réellement essayé de sortir.

## 2.3 La machine et le clavier

La machine est un mini-PC (NUC) accroché au mur, allumé plusieurs jours dans un lieu public, sans personne à côté.

Le clavier sert à choisir un persona. Mais un clavier reste un clavier : il envoie n'importe quelle touche à n'importe quel programme, et rien n'empêche un visiteur de s'en servir pour sortir de l'œuvre et atteindre le système. La machine elle-même est à portée de main, avec ses ports et son bouton d'alimentation.

Et comme il y a deux enceintes, une IA détournée ne se contente pas d'afficher n'importe quoi : elle peut le dire à voix haute, devant le public.

## 2.4 Les risques

| Ce qui peut arriver | À cause de quoi | Gravité |
| --- | --- | --- |
| Un visiteur sort de l'œuvre et atteint le système | Clavier mural | Élevée |
| La machine s'arrête et ne repart pas | Panne, coupure de courant | Élevée |
| La machine renseigne l'extérieur sur elle-même et sur le réseau | Mises à jour, services qui se signalent | Moyenne |
| Une clé d'API se retrouve sur GitHub | Erreur dans un commit | Moyenne |
| Le score affiché ne correspond pas à la réponse donnée | Score non vérifié avant affichage | Moyenne |

La panne n'est pas une attaque, mais son effet est identique : l'œuvre ne fonctionne plus. Pendant une exposition, elle est plus probable qu'une intrusion. C'est le risque qui justifie les sauvegardes.

# 3\. Le NUC et son pare-feu : ce qui existe déjà

Le NUC constitue le cœur physique et logique de l’installation Frugal Training. Étant déployé sur le lieu d'exposition, il héberge à la fois le système d'exploitation, l'environnement d'exécution de l'IA locale, les deux bases de données et l'interface utilisateur.

## 3.1 État des lieux du système d'exploitation et des services

Avant toute modification, le NUC dispose d'une configuration par défaut qu'il convient de durcir :

-   **Système d'exploitation :** Un système Linux (ex: Ubuntu Server / Debian) est à privilégier par rapport à Windows pour limiter la surface d'attaque, la consommation de ressources matérielles et les flux télémétriques incontrôlés.
    
-   **Services résidents :** Par défaut, plusieurs services réseau (SSH, mDNS/Avahi, clients de mise à jour automatique) peuvent être actifs et écouter sur les interfaces réseau.
    
-   **Comptes et privilèges :** Présence d'un compte utilisateur principal ayant potentiellement des droits `sudo` sans restriction, représentant un risque en cas de prise de contrôle locale.
    

## 3.2 Filtrage local (Pare-feu hôte)

Le pare-feu local du NUC (`nftables` ou `ufw`) constitue la première ligne de défense interne. Sa politique par défaut doit être strictement définie selon le principe du moindre privilège : **Tout bloquer par défaut, autoriser uniquement le strict nécessaire.**

### Règles de filtrage entrant

-   **Trafic local/boucle locale :** Autorisé sans restriction (nécessaire pour la communication entre l'interface graphique, l'IA locale et les bases de données hébergées sur le même NUC).
    
-   **Flux de gestion (SSH) :** Bloqué par défaut sur l'interface publique. Il ne doit être autorisé que depuis une plage d'IP d'administration dédiée ou temporairement via une interface physique spécifique lors des phases de maintenance.
    
-   **Flux applicatifs :** Aucun port entrant n'a besoin d'être exposé au réseau du lieu d'exposition si l'IHM tourne localement sur le NUC.
    

### Règles de filtrage sortant

-   **APIs d'IA publiques :** Autoriser uniquement le trafic HTTPS (port TCP 443) à destination des noms de domaine ou blocs IP strictement identifiés des fournisseurs d'IA (ex: API Mistral, OpenAI, Google Gemini).
    
-   **Résolution DNS :** Autoriser le port UDP/TCP 53 uniquement vers les serveurs DNS de confiance configurés.
    
-   **NTP (Synchronisation horaire) :** Autoriser le port UDP 123 pour garantir l'horodatage correct des logs d'erreurs et de sécurité.
    
-   **Tout autre flux sortant :** Bloqué (interdiction de la télémétrie OS, des mises à jour non planifiées en plein festival et des connexions vers des domaines tiers).

# 5\. Résister à quelqu'un qui a la machine à portée de main
 
Le NUC est accroché au mur, et le clavier à disposition de tous. Le public a donc accès à deux choses : les touches, et la machine elle-même. Ce ne sont pas les mêmes risques et ils ne se traitent pas pareil.
 
Ces risques viennent de l'accès physique, pas du système installé. Ce sont les outils pour s'en protéger qui changent d'un système à l'autre.
 
## 5.1 Actions possibles depuis le clavier
 
Ces actions ne demandent aucune compétence technique.
 
| Ce qu'il peut faire | Exemple |
| --- | --- |
| Ouvrir une autre page dans le navigateur, y compris les pages de configuration de la machine | `Ctrl+T` puis une adresse |
| Sortir du plein écran et voir le bureau | `F11` ou `Échap` |
| Passer sur une autre fenêtre ouverte | `Alt+Tab` |
| Fermer l'application | `Alt+F4` |
| Lancer n'importe quel programme | `Win+R` |
| Ouvrir l'explorateur de fichiers | `Win+E` |
| Ouvrir le menu du système | Touche Windows |
| Ouvrir le gestionnaire de tâches, pour fermer l'application ou en lancer une autre | `Ctrl+Shift+Échap` |
| Atteindre l'écran de sécurité du système | `Ctrl+Alt+Suppr` |
| Basculer sur une console texte, en dehors de l'interface graphique | `Ctrl+Alt+F2` sous Linux |
 
Les touches changent d'un système à l'autre, les possibilités non.
 
Le gestionnaire de tâches sert à fermer l'application ou à en lancer une autre. `Ctrl+Alt+Suppr` est un cas à part : le système le traite avant tout le reste, on ne peut pas le neutraliser comme un raccourci normal, et seul le mode kiosque limite ce qu'on y trouve.
 
Il existe des dizaines d'autres raccourcis, sans compter le clic droit et les menus. Un seul qui reste actif suffit pour sortir de l'œuvre, donc les bloquer un par un ne marchera jamais. On verrouille plutôt la session sur une seule application, et tout ce qui n'était pas prévu est refusé. C'est la même logique que pour le pare-feu : on liste ce qui est autorisé, pas ce qui est interdit.