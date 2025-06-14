### Le Guide du Développeur Intelligent : Notre Nouvelle Méthode de Travail

Après les frustrations que nous avons vécues, nous avons adopté une méthode de développement professionnelle, plus stable et plus efficace. Ce guide explique pourquoi et comment l'utiliser.

#### 1. La Philosophie : Pourquoi cette méthode ?

Le problème fondamental que nous avons rencontré est le syndrome du **"ça marche sur ma machine"**. L'environnement de votre MacBook (avec ses propres versions de logiciels, ses propres chemins) est différent de l'environnement de production sur Render. Cela a créé des bugs imprévisibles et frustrants.

La solution est de s'assurer que l'environnement de développement est **un clone parfait** de l'environnement de production. C'est exactement ce que Docker nous permet de faire.

#### 2. L'Ancienne vs. la Nouvelle Méthode

*   **L'Ancienne Méthode (Manuelle) :** Nous utilisions `docker build` pour créer l'image, puis `docker run` pour la lancer.
    *   *Le problème :* C'était lent. À chaque modification du code, il fallait arrêter, reconstruire et relancer manuellement. Pas de rechargement automatique.

*   **La Nouvelle Méthode (Automatisée avec `docker-compose`) :** Nous utilisons maintenant un "chef d'orchestre" nommé `docker-compose`.
    *   *La solution :* Il lit un fichier de recette (`docker-compose.yml`) qui décrit notre environnement idéal. Surtout, il **synchronise en temps réel** notre code local avec le code à l'intérieur du conteneur.

**Résultat : On combine le meilleur des deux mondes. La stabilité de Docker avec la rapidité du développement local.**

#### 3. Le Guide Pratique : Comment travailler au quotidien

Il n'y a plus que 2 commandes à connaître.

##### Étape 1 : Lancer l'environnement de développement

Ouvrez un terminal à la racine du projet et tapez :

```bash
docker-compose up
```

*   **Que se passe-t-il ?** `docker-compose` va lire la recette, construire l'image si nécessaire, démarrer le conteneur, et afficher les logs de l'application en direct dans votre terminal.
*   L'application sera accessible sur **http://localhost:5001**.

##### Étape 2 : Travailler sur le code

C'est la partie magique. **Vous n'avez rien de spécial à faire.**
Ouvrez le projet dans votre éditeur de code et modifiez n'importe quel fichier (`.py`, `.html`, `.css`).
Quand vous sauvegardez un fichier Python, vous verrez le serveur se recharger tout seul dans le terminal où vous avez lancé `docker-compose up`.

##### Étape 3 : Arrêter l'environnement

Quand vous avez fini de travailler :
1.  Allez dans le terminal où l'application tourne.
2.  Appuyez sur `Ctrl + C`.
3.  Pour vous assurer que tout est bien éteint et nettoyé (conteneur, réseau...), tapez :
    ```bash
    docker-compose down
    ```

#### 4. Cas Particuliers Importants

*   **"J'ai ajouté une nouvelle librairie dans `requirements.txt`"**
    Dans ce cas, vous devez reconstruire l'image pour que la nouvelle librairie y soit installée. La commande est :
    ```bash
    docker-compose up --build
    ```

*   **"Je veux exécuter une commande à l'intérieur du conteneur"**
    Si vous avez besoin d'exécuter une commande ponctuelle (comme nos `sqlite3` ou `rm` de tout à l'heure), ouvrez un **second terminal** et tapez :
    ```bash
    docker-compose exec web bash
    ```
    Cela vous donnera un accès direct à l'intérieur du conteneur, dans un environnement Linux propre.

---

En adoptant ce flux de travail, vous développerez plus vite, avec beaucoup moins de bugs et une confiance absolue que ce qui fonctionne chez vous fonctionnera en production. 