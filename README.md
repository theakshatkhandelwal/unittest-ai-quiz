# UniTest - AI-Powered Learning Platform

UniTest is a comprehensive AI-powered learning platform that generates personalized quizzes using advanced AI models. It features Bloom's Taxonomy progression, intelligent assessment, and progress tracking to create an adaptive learning experience.

## 🌟 Features

- **AI-Generated Questions**: Intelligent, context-aware questions for any topic
- **Bloom's Taxonomy**: Progress through cognitive levels from basic to advanced
- **Multiple Question Types**: MCQ, subjective questions, or a combination
- **Smart Assessment**: AI-powered evaluation of subjective answers
- **Progress Tracking**: Monitor learning journey across topics
- **Document Upload**: Upload study materials for automatic topic extraction
- **Responsive Design**: Modern, mobile-friendly interface
- **PDF Export**: Download quizzes for offline study

## 🚀 Live Demo

**Deploy your own instance or use the live demo:**

- **Heroku**: [Deploy to Heroku](#deploy-to-heroku)
- **Railway**: [Deploy to Railway](#deploy-to-railway)
- **Render**: [Deploy to Render](#deploy-to-render)

## 🛠️ Technology Stack

- **Backend**: Python Flask
- **Database**: SQLAlchemy with SQLite/PostgreSQL
- **AI**: Google Generative AI (Gemini)
- **Frontend**: Bootstrap 5, HTML5, CSS3, JavaScript
- **Authentication**: Flask-Login
- **PDF Generation**: ReportLab
- **Document Processing**: PyPDF2, NLTK

## 📋 Prerequisites

- Python 3.8+
- Google AI API Key (from [Google AI Studio](https://makersuite.google.com/app/apikey))
- Git

## 🚀 Quick Start (Local Development)

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd unittest
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables
Create a `.env` file in the root directory:
```bash
SECRET_KEY=your-secret-key-here
GOOGLE_AI_API_KEY=your-google-ai-api-key-here
DATABASE_URL=sqlite:///unittest.db
```

### 5. Run the Application
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## 🌐 Deployment Options

### Deploy to Heroku

1. **Install Heroku CLI** and login:
```bash
heroku login
```

2. **Create Heroku App**:
```bash
heroku create your-unittest-app
```

3. **Set Environment Variables**:
```bash
heroku config:set SECRET_KEY=your-secret-key-here
heroku config:set GOOGLE_AI_API_KEY=your-google-ai-api-key-here
```

4. **Add PostgreSQL** (recommended for production):
```bash
heroku addons:create heroku-postgresql:mini
```

5. **Deploy**:
```bash
git add .
git commit -m "Initial deployment"
git push heroku main
```

6. **Open your app**:
```bash
heroku open
```

### Deploy to Railway

1. **Connect your GitHub repository** to Railway
2. **Set environment variables** in Railway dashboard
3. **Deploy automatically** on every push

### Deploy to Render

1. **Create a new Web Service** on Render
2. **Connect your GitHub repository**
3. **Set environment variables**:
   - `SECRET_KEY`
   - `GOOGLE_AI_API_KEY`
   - `DATABASE_URL` (use Render's PostgreSQL)
4. **Deploy**

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `SECRET_KEY` | Flask secret key for sessions | Yes | - |
| `GOOGLE_AI_API_KEY` | Google AI API key | Yes | - |
| `DATABASE_URL` | Database connection string | No | `sqlite:///unittest.db` |
| `FLASK_ENV` | Flask environment | No | `development` |

### Database Configuration

The application supports both SQLite (development) and PostgreSQL (production):

- **SQLite**: Good for development and small deployments
- **PostgreSQL**: Recommended for production deployments

## 📱 Usage

### For Students/Learners

1. **Sign Up**: Create a free account
2. **Choose Topic**: Enter any subject you want to learn
3. **Take Quiz**: Answer AI-generated questions
4. **Track Progress**: Monitor your learning journey
5. **Advance Levels**: Progress through Bloom's Taxonomy

### For Educators

1. **Create Quizzes**: Generate questions for any topic
2. **Customize Questions**: Choose question types and counts
3. **Monitor Progress**: Track student learning outcomes
4. **Export Quizzes**: Download PDF versions for offline use

## 🔒 Security Features

- **Password Hashing**: Secure password storage using Werkzeug
- **Session Management**: Secure user sessions with Flask-Login
- **Input Validation**: Form validation and sanitization
- **CSRF Protection**: Built-in CSRF protection with Flask-WTF

## 📊 Performance

- **AI Response Time**: Optimized for quick question generation
- **Database Queries**: Efficient database operations with SQLAlchemy
- **Static Assets**: CDN-hosted Bootstrap and FontAwesome
- **Responsive Design**: Mobile-first approach for all devices

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Google AI**: For providing the Gemini AI model
- **Bootstrap**: For the responsive UI framework
- **Flask**: For the web framework
- **Open Source Community**: For various Python packages

## 📞 Support

If you have any questions or need help with deployment:

1. **Check the documentation** above
2. **Open an issue** on GitHub
3. **Contact the developer** for personalized support

## 🚀 Ready to Deploy?

Your UniTest application is now ready for deployment! Choose your preferred platform and follow the deployment instructions above. Once deployed, you'll have a professional, AI-powered learning platform that you can proudly showcase on your resume.

**Happy Learning! 🎓✨**
