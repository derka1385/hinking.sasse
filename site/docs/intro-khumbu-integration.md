# Montagne approuvée dans l’intro — aperçu local

La page d’accueil utilise le relief approuvé dans `site/mountain-lab.html`. Le binaire et sa géométrie sont conservés intégralement. Le reste du site, ses textes et ses styles sont conservés.

## Revoir les versions

- Nouvelle intro : `http://127.0.0.1:4174/?intro`
- Vue d’inspection pendant l’approche : `http://127.0.0.1:4174/?p=0.36`
- Ancienne intro indépendante : `http://127.0.0.1:4174/archive/intro-before-khumbu-2026-10-02/?intro`

Le serveur Python est lié à `127.0.0.1` et sert le projet local. Le port 4173 était utilisé par un autre projet. Aucun commit ni push n’a été effectué.

## Modèle et animation

`intro-khumbu.js` charge `khumbu.json` et `khumbu.bin`, puis applique une échelle uniforme de 1 000 mètres par kilomètre de relief, une rotation Y de +0,159 radian et une translation qui place le sommet principal sur l’ancrage de l’animation existante. Cette rotation correspond à l’angle de la vue de référence fournie, relevé dans le laboratoire ouvert. La forme du relief n’est pas régénérée.

Les clés de caméra, le champ de vision, l’interpolation, le rythme du scroll, le mouvement au repos, la cordée, le son et la transition vers la page sont conservés. Les grimpeurs sont projetés sur la nouvelle paroi. La marge de sécurité de la caméra prend en compte son mouvement au repos, pour éviter de traverser le terrain.

Le relief est dessiné comme un maillage, puis l’intro applique le brouillard et les nuages d’origine. La distance du maillage masque les grimpeurs cachés par la roche. Les ombres suivent la lumière de l’intro et sont réutilisées lorsque sa direction ne change pas. Le mobile utilise un échantillonnage du même relief (235 266 triangles contre 941 064 sur ordinateur).

## Atmosphère publiée

Source vérifiée sur la branche publiée `main` du remote `hiking` :
`595da573f2d1ac9b3bc489cc05bb9d5cb142c063`.

Les clés de lumière et de brouillard, leur interpolation, le volume de bruit, les fonctions de brouillard, les nuages animés, la courbe de film et les shaders de neige proviennent de cette version. Les matières roche/neige du modèle approuvé reçoivent cette lumière. La copie Git de référence est conservée dans l’archive.

## Validation

- `node site/tools/check_khumbu_integration.mjs` : identité du modèle, 68 fichiers archivés intacts, blocs atmosphériques identiques au Git publié, animation comparée sur 6 003 échantillons, six grimpeurs sur le terrain, continuité et absence de collision de la caméra.
- `node site/tools/check_intro.mjs` : chargement asynchrone, Skip pendant chargement, chargement interrompu/indisponible, reduced motion, absence WebGL, replay, fin unique et libération du renderer.
- Vérification WebGL2 réelle sur ordinateur et à 390 × 844 ; bouton Skip essayé dans le navigateur ; aucun avertissement ni erreur WebGL/JavaScript observé.
- Le scan de design ne relève aucun problème dans les deux scripts modifiés. Ses alertes HTML concernent les styles existants, conservés dans cette intervention.

Captures : `intro-khumbu-desktop.jpg`, `intro-khumbu-mobile.jpg`.

L’archive contient la page d’accueil et ses ressources nécessaires pour rejouer l’ancien modèle ; son README décrit la restauration.

## Netteté et stabilité pendant l’approche

Le rendu démarre désormais à la résolution de l’écran, plafonnée à 1,75× sur ordinateur et 1,5× sur mobile, avec des budgets de 2,8 / 1,2 millions de pixels. L’adaptation ne descend plus sous un pixel de rendu par pixel CSS, sauf si le budget maximal impose une limite sur un écran très grand.

Le terrain possède son propre framebuffer multisamplé (4× ordinateur, 2× mobile, selon les capacités WebGL2), résolu en couleur et distance. Les pixels partiellement couverts sont composités correctement avec le ciel. La projection du terrain utilise un plan proche de 3 m, ce qui améliore de 30× la précision du depth buffer à distance ; la projection des flocons reste inchangée.

Les octaves de microrelief et les veinures sont filtrées selon leur empreinte à l’écran. Les perturbations des normales sont bornées et s’atténuent lorsque leurs détails deviennent plus petits qu’un pixel. Les textures utilisent les mipmaps et le filtrage anisotrope disponible. Les ombres utilisent une carte 4096² / 2048² et des comparaisons de profondeur filtrées ; les petits déplacements du soleil actualisent les ombres sans l’ancien palier de direction.

Tests supplémentaires : resolve MSAA des deux sorties après resize, réutilisation des ombres au repos, actualisation pour une variation fine du soleil et séparation de deux surfaces distantes dans le depth buffer. Géométrie, animation et blocs atmosphériques publiés restent identiques.
