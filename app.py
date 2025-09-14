import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import json
import re
import PyPDF2
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from collections import Counter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
from datetime import datetime

# Download NLTK data
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
# Database configuration - use PostgreSQL on Vercel/NeonDB, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    # Fix for Vercel/NeonDB PostgreSQL URL format
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
elif database_url and database_url.startswith('postgresql://'):
    # Already in correct format for NeonDB
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///unittest.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configure Google AI
genai.configure(api_key=os.environ.get('GOOGLE_AI_API_KEY', 'AIzaSyBTdFaUX_xjPLAnhrZDUY0KaZ07aI3UvY8'))

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(100), nullable=False)
    bloom_level = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def evaluate_subjective_answer(question, student_answer, model_answer):
    """Use AI to evaluate subjective answers"""
    if not genai or not student_answer.strip():
        return 0.0

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""
        Evaluate this student's answer for the given question:

        Question: {question}
        Student Answer: {student_answer}
        Model Answer: {model_answer}

        Rate the student's answer on a scale of 0.0 to 1.0 based on:
        - Accuracy and correctness
        - Completeness
        - Understanding demonstrated
        - Relevance to the question

        Return only a number between 0.0 and 1.0 (e.g., 0.8 for 80% correct)
        """

        response = model.generate_content(prompt)
        score_text = response.text.strip()

        # Extract number from response
        score_match = re.search(r'(\d*\.?\d+)', score_text)
        if score_match:
            score = float(score_match.group(1))
            return min(max(score, 0.0), 1.0)  # Clamp between 0 and 1

        return 0.5  # Default if can't parse
    except Exception as e:
        print(f"Error in evaluate_subjective_answer: {str(e)}")
        return 0.5  # Default on error

def get_difficulty_from_bloom_level(bloom_level):
    """Map Bloom's taxonomy level to difficulty level"""
    if bloom_level <= 2:
        return "beginner"
    elif bloom_level <= 4:
        return "intermediate"
    else:
        return "difficult"

def generate_quiz(topic, difficulty_level, question_type="mcq", num_questions=5):
    if not genai:
        return None

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        # Map difficulty levels to Bloom's taxonomy levels and descriptions
        difficulty_mapping = {
            "beginner": {
                "bloom_level": 1,
                "description": "Remembering and Understanding level - basic facts, definitions, and simple concepts"
            },
            "intermediate": {
                "bloom_level": 3,
                "description": "Applying and Analyzing level - practical application and analysis of concepts"
            },
            "difficult": {
                "bloom_level": 5,
                "description": "Evaluating and Creating level - critical thinking, evaluation, and synthesis"
            }
        }
        
        difficulty_info = difficulty_mapping.get(difficulty_level, difficulty_mapping["beginner"])
        bloom_level = difficulty_info["bloom_level"]
        level_description = difficulty_info["description"]
        
        # Add randomization seed to prompt for variety
        import random
        random_seed = random.randint(1000, 9999)

        if question_type == "mcq":
            prompt = f"""
                Generate a multiple-choice quiz on {topic} at {difficulty_level.upper()} level ({level_description}).
                - Include exactly {num_questions} questions.
                - Each question should have 4 answer choices.
                - Make questions diverse and varied - avoid repetitive patterns.
                - Use randomization seed {random_seed} to ensure variety.
                - Include a "level" key specifying the Bloom's Taxonomy level (Remembering, Understanding, Applying, etc.).
                - Return output in valid JSON format: 
                [
                    {{"question": "What is AI?", "options": ["A. option1", "B. option2", "C. option3", "D. option4"], "answer": "A", "type": "mcq"}},
                    ...
                ]
            """
        else:  # subjective
            prompt = f"""
                Generate subjective questions on {topic} at {difficulty_level.upper()} level ({level_description}).
                - Include exactly {num_questions} questions.
                - Questions should be open-ended and require detailed answers.
                - Make questions diverse and varied - avoid repetitive patterns.
                - Use randomization seed {random_seed} to ensure variety.
                - Include a "level" key specifying the Bloom's Taxonomy level.
                - Vary the marks between 5, 10, 15, and 20 marks for different questions.
                - Return output in valid JSON format: 
                [
                    {{"question": "Explain the concept of AI and its applications", "answer": "Sample answer explaining AI...", "type": "subjective", "marks": 10}},
                    ...
                ]
            """

        response = model.generate_content(prompt)

        if not response.text:
            raise ValueError("Empty response from AI")

        json_match = re.search(r"```json\n(.*)\n```", response.text, re.DOTALL)
        if json_match:
            questions = json.loads(json_match.group(1))
        else:
            try:
                questions = json.loads(response.text)
            except:
                raise ValueError("Invalid response format from AI")

        return questions

    except Exception as e:
        print(f"Error in generate_quiz: {str(e)}")
        return None

def process_document(file_path):
    """Process uploaded document to extract content"""
    try:
        content = ""
        if file_path.lower().endswith('.pdf'):
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    content += page.extract_text()
        else:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

        if not content.strip():
            return None

        tokens = word_tokenize(content.lower())
        stop_words = set(stopwords.words('english'))
        meaningful_words = [word for word in tokens if word.isalnum() and word not in stop_words]

        if not meaningful_words:
            return None

        word_freq = Counter(meaningful_words)
        main_topic = word_freq.most_common(1)[0][0].capitalize()
        return main_topic

    except Exception as e:
        print(f"Error processing document: {str(e)}")
        return None

# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/sitemap.xml')
def sitemap():
    return send_file('static/sitemap.xml', mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    return send_file('static/robots.txt', mimetype='text/plain')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            confirm_password = request.form['confirm_password']

            if not all([username, email, password, confirm_password]):
                flash('Please fill in all fields', 'error')
                return redirect(url_for('signup'))

            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return redirect(url_for('signup'))

            if db.session.query(User).filter_by(username=username).first():
                flash('Username already exists', 'error')
                return redirect(url_for('signup'))

            if db.session.query(User).filter_by(email=email).first():
                flash('Email already exists', 'error')
                return redirect(url_for('signup'))

            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()

            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error in signup: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']

            user = db.session.query(User).filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            print(f"Error in login: {str(e)}")
            flash('An error occurred. Please try again.', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    progress_records = db.session.query(Progress).filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', progress_records=progress_records)

@app.route('/quiz', methods=['GET', 'POST'])
@login_required
def quiz():
    if request.method == 'GET':
        # Handle topic parameter from AI learning modal or next/retry level
        topic = request.args.get('topic', '')
        difficulty = request.args.get('difficulty', '')
        action = request.args.get('action', '')
        
        if topic:
            return render_template('quiz.html', 
                                 prefill_topic=topic, 
                                 prefill_difficulty=difficulty,
                                 action=action)
    
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        question_type = request.form.get('question_type', 'mcq')
        mcq_count = int(request.form.get('mcq_count', 3))
        subj_count = int(request.form.get('subj_count', 2))
        difficulty_level = request.form.get('difficulty_level', 'beginner')
        
        # Check if PDF file was uploaded
        if 'file_upload' in request.files and request.files['file_upload'].filename:
            file = request.files['file_upload']
            if file and file.filename.lower().endswith('.pdf'):
                try:
                    # Save file temporarily
                    import tempfile
                    import os
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                        file.save(tmp_file.name)
                        tmp_path = tmp_file.name
                    
                    # Process the PDF to extract topic
                    extracted_topic = process_document(tmp_path)
                    
                    # Clean up temporary file
                    os.unlink(tmp_path)
                    
                    if extracted_topic:
                        topic = extracted_topic
                        flash(f'Topic extracted from PDF: {topic}', 'success')
                    else:
                        flash('Could not extract topic from PDF. Please enter a topic manually.', 'error')
                        return redirect(url_for('quiz'))
                        
                except Exception as e:
                    flash(f'Error processing PDF: {str(e)}', 'error')
                    return redirect(url_for('quiz'))
        
        # Ensure we have a topic
        if not topic:
            flash('Please either enter a topic OR upload a PDF file.', 'error')
            return redirect(url_for('quiz'))

        # Get user's current bloom level for this topic (for progress tracking)
        progress = db.session.query(Progress).filter_by(user_id=current_user.id, topic=topic).first()
        bloom_level = progress.bloom_level if progress else 1

        # Generate questions using difficulty level
        questions = []
        if question_type == "both":
            mcq_questions = generate_quiz(topic, difficulty_level, "mcq", mcq_count)
            subj_questions = generate_quiz(topic, difficulty_level, "subjective", subj_count)
            if mcq_questions and subj_questions:
                questions = mcq_questions + subj_questions
        else:
            num_q = mcq_count if question_type == "mcq" else subj_count
            questions = generate_quiz(topic, difficulty_level, question_type, num_q)

        if questions:
            session['current_quiz'] = {
                'questions': questions,
                'topic': topic,
                'bloom_level': bloom_level,
                'difficulty_level': difficulty_level
            }
            return redirect(url_for('take_quiz'))
        else:
            flash('Failed to generate quiz questions', 'error')

    return render_template('quiz.html')

@app.route('/take_quiz')
@login_required
def take_quiz():
    quiz_data = session.get('current_quiz')
    if not quiz_data:
        flash('No quiz available', 'error')
        return redirect(url_for('quiz'))
    
    return render_template('take_quiz.html', quiz_data=quiz_data)

@app.route('/submit_quiz', methods=['POST'])
@login_required
def submit_quiz():
    quiz_data = session.get('current_quiz')
    if not quiz_data:
        return jsonify({'error': 'No quiz available'})

    questions = quiz_data['questions']
    topic = quiz_data['topic']
    bloom_level = quiz_data['bloom_level']
    difficulty_level = quiz_data.get('difficulty_level', 'beginner')
    
    # Get answers for each question
    user_answers = []
    for i in range(len(questions)):
        question = questions[i]
        if question.get('type') == 'mcq':
            # For MCQ questions, get from question group
            answer = request.form.get(f'question_{i}')
        else:
            # For subjective questions, get from subjective_answers array
            answer = request.form.get(f'subjective_answers[{i}]')
        
        if not answer:
            return jsonify({'error': f'Please answer question {i+1}'})
        user_answers.append(answer)

    # Calculate scores
    correct_answers = 0
    total_marks = 0
    scored_marks = 0
    results = []

    for i, (q, user_ans) in enumerate(zip(questions, user_answers)):
        if q.get('type') == 'mcq':
            user_choice = user_ans.split(". ")[0] if user_ans else ""
            is_correct = user_choice == q["answer"]
            if is_correct:
                correct_answers += 1
            results.append({
                'question': q['question'],
                'user_answer': user_ans,
                'correct_answer': next((opt for opt in q["options"] if opt.startswith(f"{q['answer']}.")), ""),
                'is_correct': is_correct,
                'type': 'mcq'
            })
        else:  # subjective
            marks = q.get('marks', 10)
            total_marks += marks
            
            if user_ans.strip():
                ai_score = evaluate_subjective_answer(q['question'], user_ans, q.get('answer', ''))
                scored_marks += ai_score * marks
                if ai_score >= 0.6:
                    correct_answers += 1
            else:
                ai_score = 0.0

            results.append({
                'question': q['question'],
                'user_answer': user_ans,
                'sample_answer': q.get('answer', 'N/A'),
                'marks': marks,
                'ai_score': ai_score,
                'scored_marks': ai_score * marks,
                'type': 'subjective'
            })

    # Calculate final score
    has_subjective = any(q.get('type') == 'subjective' for q in questions)
    
    if has_subjective:
        percentage = (scored_marks / total_marks) * 100 if total_marks > 0 else 0
        passed = percentage >= 60
        final_score = f"{scored_marks:.1f}/{total_marks} marks"
    else:
        percentage = (correct_answers / len(questions)) * 100 if questions else 0
        passed = percentage >= 60
        final_score = f"{correct_answers}/{len(questions)}"

    # Update progress
    progress = db.session.query(Progress).filter_by(user_id=current_user.id, topic=topic).first()
    if progress:
        if passed and bloom_level + 1 > progress.bloom_level:
            progress.bloom_level = bloom_level + 1
    else:
        new_progress = Progress(
            user_id=current_user.id,
            topic=topic,
            bloom_level=bloom_level + 1 if passed else bloom_level
        )
        db.session.add(new_progress)
    
    db.session.commit()

    # Clear quiz session
    session.pop('current_quiz', None)

    return render_template('quiz_results.html', 
                         results=results, 
                         final_score=final_score, 
                         percentage=percentage, 
                         passed=passed,
                         topic=topic,
                         bloom_level=bloom_level,
                         difficulty_level=difficulty_level)

@app.route('/next_level', methods=['POST'])
@login_required
def next_level():
    """Automatically generate next level quiz and redirect to take_quiz"""
    try:
        topic = request.form.get('topic', '').strip()
        difficulty_level = request.form.get('difficulty_level', 'beginner').strip()
        
        if not topic:
            flash('Topic is required', 'error')
            return redirect(url_for('quiz'))
        
        # Determine next difficulty level
        difficulty_mapping = {
            "beginner": "intermediate",
            "intermediate": "difficult", 
            "difficult": "difficult"  # Stay at difficult if already at highest level
        }
        next_difficulty = difficulty_mapping.get(difficulty_level, "intermediate")
        
        # Generate questions for next level
        questions = generate_quiz(topic, next_difficulty, "mcq", 5)
        
        if questions:
            session['current_quiz'] = {
                'questions': questions,
                'topic': topic,
                'bloom_level': 1,  # This will be updated based on difficulty
                'difficulty_level': next_difficulty
            }
            flash(f'Generated {next_difficulty.title()} level quiz for {topic}!', 'success')
            return redirect(url_for('take_quiz'))
        else:
            flash('Failed to generate next level quiz', 'error')
            return redirect(url_for('quiz'))
    except Exception as e:
        print(f"Error in next_level: {str(e)}")
        flash('An error occurred while generating the next level quiz', 'error')
        return redirect(url_for('quiz'))

@app.route('/retry_level', methods=['POST'])
@login_required
def retry_level():
    """Automatically generate retry quiz and redirect to take_quiz"""
    try:
        topic = request.form.get('topic', '').strip()
        difficulty_level = request.form.get('difficulty_level', 'beginner').strip()
        
        if not topic:
            flash('Topic is required', 'error')
            return redirect(url_for('quiz'))
        
        # Generate questions for the same level
        questions = generate_quiz(topic, difficulty_level, "mcq", 5)
        
        if questions:
            session['current_quiz'] = {
                'questions': questions,
                'topic': topic,
                'bloom_level': 1,  # This will be updated based on difficulty
                'difficulty_level': difficulty_level
            }
            flash(f'Generated new {difficulty_level.title()} level quiz for {topic}!', 'success')
            return redirect(url_for('take_quiz'))
        else:
            flash('Failed to generate retry quiz', 'error')
            return redirect(url_for('quiz'))
    except Exception as e:
        print(f"Error in retry_level: {str(e)}")
        flash('An error occurred while generating the retry quiz', 'error')
        return redirect(url_for('quiz'))

@app.route('/continue_learning', methods=['POST'])
@login_required
def continue_learning():
    """Continue learning from where user left off based on their progress"""
    try:
        topic = request.form.get('topic', '').strip()
        
        if not topic:
            flash('Topic is required', 'error')
            return redirect(url_for('dashboard'))
        
        # Get user's current progress for this topic
        progress = db.session.query(Progress).filter_by(user_id=current_user.id, topic=topic).first()
        
        if not progress:
            flash('No progress found for this topic', 'error')
            return redirect(url_for('dashboard'))
        
        # Map bloom level to difficulty level
        difficulty_level = get_difficulty_from_bloom_level(progress.bloom_level)
        
        # Generate questions for the current level
        questions = generate_quiz(topic, difficulty_level, "mcq", 5)
        
        if questions:
            session['current_quiz'] = {
                'questions': questions,
                'topic': topic,
                'bloom_level': progress.bloom_level,
                'difficulty_level': difficulty_level
            }
            flash(f'Continuing {topic} at {difficulty_level.title()} level (Bloom Level {progress.bloom_level})!', 'success')
            return redirect(url_for('take_quiz'))
        else:
            flash('Failed to generate quiz for continuing learning', 'error')
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error in continue_learning: {str(e)}")
        flash('An error occurred while continuing your learning', 'error')
        return redirect(url_for('dashboard'))

@app.route('/upload_pdf', methods=['POST'])
@login_required
def upload_pdf():
    """Handle PDF upload and extract topic"""
    if 'file_upload' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file_upload']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file and file.filename.lower().endswith('.pdf'):
        try:
            # Save file temporarily
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                file.save(tmp_file.name)
                tmp_path = tmp_file.name
            
            # Process the PDF to extract topic
            topic = process_document(tmp_path)
            
            # Clean up temporary file
            os.unlink(tmp_path)
            
            if topic:
                return jsonify({'success': True, 'topic': topic})
            else:
                return jsonify({'success': False, 'error': 'Could not extract topic from PDF'})
                
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error processing PDF: {str(e)}'})
    
    return jsonify({'success': False, 'error': 'Invalid file format. Please upload a PDF.'})

@app.route('/ai_learn', methods=['POST'])
@login_required
def ai_learn():
    """AI-powered learning content generation"""
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip()
        level = data.get('level', 'intermediate')
        style = data.get('style', 'theoretical')
        
        if not topic:
            return jsonify({'success': False, 'error': 'Topic is required'})
        
        # Generate learning content using AI
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""
        Create a personalized learning path for {topic} at {level} level, 
        focusing on {style} learning style.
        
        IMPORTANT: You MUST use this EXACT format with these EXACT section headers:
        
        ## OVERVIEW
        [Write a brief 2-3 sentence overview of the topic here]
        
        ## KEY CONCEPTS
        • [Write concept 1 with brief explanation here]
        • [Write concept 2 with brief explanation here]
        • [Write concept 3 with brief explanation here]
        
        ## LEARNING OBJECTIVES
        ✓ [Write objective 1 here]
        ✓ [Write objective 2 here]
        ✓ [Write objective 3 here]
        
        ## STUDY APPROACH
        [Write practical study recommendations based on {style} learning style here]
        
        ## COMMON MISCONCEPTIONS
        ⚠️ [Write misconception 1 and why it's wrong here]
        ⚠️ [Write misconception 2 and why it's wrong here]
        
        ## NEXT STEPS
        [Write what to do after understanding these basics here]
        
        CRITICAL: Start your response immediately with "## OVERVIEW" and follow the exact format above. Do not add any introductory text or explanations before the sections.
        """
        
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        return jsonify({'success': True, 'content': content})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error generating learning content: {str(e)}'})

@app.route('/download_pdf')
@login_required
def download_pdf():
    quiz_data = session.get('current_quiz')
    if not quiz_data:
        return jsonify({'error': 'No quiz available'})

    questions = quiz_data['questions']
    topic = quiz_data['topic']
    bloom_level = quiz_data['bloom_level']

    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30
    )
    question_style = ParagraphStyle(
        'Question',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        textColor=colors.black
    )
    option_style = ParagraphStyle(
        'Option',
        parent=styles['Normal'],
        fontSize=11,
        leftIndent=20,
        spaceAfter=6,
        textColor=colors.black
    )
    
    content = []
    content.append(Paragraph(f"Quiz: {topic}", title_style))
    content.append(Paragraph(f"Bloom's Taxonomy Level: {bloom_level}", styles['Heading2']))
    content.append(Spacer(1, 20))
    
    for i, q in enumerate(questions, 1):
        question_text = f"Q{i}. {q['question']}"
        content.append(Paragraph(question_text, question_style))
        
        if q.get('type') == 'mcq':
            for opt in q['options']:
                option_text = f"□ {opt}"
                content.append(Paragraph(option_text, option_style))
        else:
            content.append(Paragraph(f"Marks: {q.get('marks', 10)}", option_style))
            content.append(Paragraph("Answer: ________________________", option_style))
        
        content.append(Spacer(1, 20))
    
    doc.build(content)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Quiz_{topic}_Level{bloom_level}.pdf",
        mimetype='application/pdf'
    )

# Error handlers
@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('error.html', error="Internal Server Error"), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error="Page Not Found"), 404

# Ensure database is created
with app.app_context():
    try:
        db.create_all()
        print("Database initialized successfully!")
        print(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    except Exception as e:
        print(f"Database initialization error: {str(e)}")
        # Continue running the app even if database fails

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

