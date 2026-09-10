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