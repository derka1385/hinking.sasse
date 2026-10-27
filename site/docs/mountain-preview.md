# Aperçu local de la montagne

Depuis la racine du projet :

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Ouvrir `http://127.0.0.1:4173/site/mountain-lab.html`.

La scène est indépendante de l’introduction existante. Glisser pour tourner,
faire défiler ou utiliser le curseur pour avancer. Les flèches permettent de
tourner au clavier, `+` et `−` d’avancer/reculer, `R` de réinitialiser.

Le maillage provient des données Copernicus du Khumbu déjà présentes dans
`site/blender/khumbu`. Le relief prétraité de l’Ama Dablam est intégré dans une
surface continue avec les contreforts et les vallées. Les textures, la neige
et l’éclairage sont une interprétation graphique, pas une photographie ni
une reconstruction photogrammétrique. Aucun fichier Blender n’est remplacé.

Tout est servi localement : JavaScript, polices, matière et relief. Pas de CDN.
Le relief quantifié représente 3,8 Mo, avec moins de 8 cm d’erreur ajoutée par
la quantification, sur des mesures sources espacées de 30 m. Les appareils à
pointeur tactile utilisent moins de triangles et une carte d’ombres réduite.
Les ombres sont calculées une seule fois, le rendu au repos est limité à
environ 30 images/s et la scène s’arrête quand l’onglet est masqué. La préférence
de mouvement réduit désactive la neige et les mouvements ambiants par défaut.

`window.mountainPreview.stats` expose des diagnostics. `cpuSubmissionMs`
mesure la soumission des commandes côté JavaScript, pas le coût GPU total.
Une photographie CC0 prend le relais si WebGL 2 est indisponible.

Pour rebâtir le relief, exécuter `site/tools/build_mountain_preview.py` avec un
Python comprenant NumPy. Le chemin de données d’origine est indiqué dans ce
script. Les crédits sont accessibles directement dans la page.
