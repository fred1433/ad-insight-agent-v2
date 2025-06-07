import pprint
from facebook_client import get_ads

def main():
    """
    Fonction principale du script.
    """
    print("Récupération des publicités depuis l'API Facebook...")
    ads = get_ads()
    
    if ads:
        print(f"{len(ads)} publicités actives trouvées.")
        pprint.pprint(ads)
    else:
        print("Aucune publicité active trouvée ou une erreur est survenue.")

if __name__ == "__main__":
    main() 