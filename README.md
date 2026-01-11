# CRAB - Advanced Voice Intelligence System

CRAB is a premium, modern AI voice assistant web application designed for a sleek and seamless user experience. It leverages advanced AI models for conversational depth and utility, featuring a high-end "Crystal-clear" UI with glassmorphism and ambient dynamic elements.

## 🚀 Features

- **Advanced AI Chat**: Powered by `pytgpt` (PHIND) and `g4f` fallback (GPT-4o), providing intelligent, context-aware responses.
- **Threaded Conversations**: Organize your interactions into distinct chat threads for better management.
- **Real-time Translation**: Instant English to Tamil translation capabilities.
- **Voice Intelligence**: Designed with voice interaction in mind (TTS/STT support ready).
- **Premium UI/UX**: A state-of-the-art interface featuring glassmorphism, smooth animations, and a responsive design.
- **Secure Authentication**: User accounts with hashed passwords and private history storage.
- **History Management**: Easily view, navigate, and delete your chat history.

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **Database**: SQLite
- **AI Integration**: `pytgpt` (PHIND), `g4f`
- **Frontend**: HTML5, Vanilla CSS (Glassmorphism), JavaScript (AJAX)
- **Translation**: `deep-translator` (Google Translate API)

## 📦 Project Structure

```text
website/
├── app.py              # Main Flask application logic & API routes
├── database.db         # SQLite database for users and chat history
├── migrate_db.py       # Database migration and schema update script
├── requirements.txt    # Python dependencies
├── static/             # CSS, JS, and image assets
└── templates/          # HTML templates (Jinaja2)
    ├── base.html       # Shared layout and navigation
    ├── home.html       # Premium landing page
    ├── index.html      # Main chat interface
    ├── login.html      # Glassmorphic login page
    └── about.html      # Project information page
```

## ⚙️ Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd website
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize the database**:
   The application automatically initializes the database on first run. To manually migrate or update:
   ```bash
   python migrate_db.py
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```
   Access the app at `http://127.0.0.1:5000`

## 👨‍💻 Developed By

**Yahya** - *Lead Developer*

---
*Created with a focus on Performance, Aesthetics, and Intelligence.*
