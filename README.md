# NEXORE Spark V3.0 — IFT Madagascar

## 🚀 Lancement rapide

```bash
# 1. Se placer dans le dossier
cd nexore

# 2. Lancer (crée le venv automatiquement)
bash lancer.sh
```

Ou manuellement :
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

## 🌐 Accès
- URL : http://localhost:5000
- Admin : `direction@ift-mada.mg` / `admin2025`

## 🔐 Rôles
| Rôle | Accès |
|------|-------|
| `direction` / `admin` | Tout + statistiques |
| `professeur` | Documents, notes, emploi du temps |
| `etudiant` | Feed, messages, emploi du temps (lecture) |

## ✅ Fonctionnalités V3.0
- ✅ Anti-duplication messages (client_id)
- ✅ Modifier / Supprimer messages
- ✅ Bulles messages corrigées mobile
- ✅ 4 thèmes (dark, light, ocean, purple)
- ✅ Afficher/masquer mot de passe
- ✅ Réactions 6 types (like, love, haha, wow, sad, angry)
- ✅ Notifications temps réel
- ✅ Indicateur "en train d'écrire"
- ✅ Emploi du temps grille responsive
- ✅ Upload fichiers messages/documents
- ✅ Annonces épinglées/urgentes
- ✅ Système amis + abonnements
- ✅ Réinitialisation mot de passe
- ✅ Base de données SQLite avec migrations auto

## 📁 Structure
```
nexore/
├── app.py              # Backend Flask complet
├── requirements.txt    # Dépendances Python
├── lancer.sh           # Script de démarrage
├── nexore.db           # Base SQLite (créée auto)
├── static/
│   └── uploads/        # Fichiers uploadés
└── templates/
    ├── index.html       # Page de connexion/inscription
    ├── app.html         # Application principale
    └── reset_password.html
```
