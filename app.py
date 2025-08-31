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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///unittest.db')
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

def generate_quiz(topic, bloom_level, question_type="mcq", num_questions=5):
    if not genai:
        return None

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")

        if question_type == "mcq":
            prompt = f"""
                Generate a multiple-choice quiz on {topic} at Bloom's Taxonomy level {bloom_level}.
                - Include exactly {num_questions} questions.
                - Each question should have 4 answer choices.
                - Include a "level" key specifying the Bloom's Taxonomy level (Remembering, Understanding, Applying, etc.).
                - Return output in valid JSON format: 
                [
                    {{"question": "What is AI?", "options": ["A. option1", "B. option2", "C. option3", "D. option4"], "answer": "A", "type": "mcq"}},
                    ...
                ]
            """
        else:  # subjective
            prompt = f"""
                Generate subjective questions on {topic} at Bloom's Taxonomy level {bloom_level}.
                - Include exactly {num_questions} questions.
                - Questions should be open-ended and require detailed answers.
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

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
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

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = db.session.query(User).filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

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
        # Handle topic parameter from AI learning modal
        topic = request.args.get('topic', '')
        if topic:
            return render_template('quiz.html', prefill_topic=topic)
    
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        question_type = request.form.get('question_type', 'mcq')
        mcq_count = int(request.form.get('mcq_count', 3))
        subj_count = int(request.form.get('subj_count', 2))
        
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

        # Get user's current bloom level for this topic
        progress = db.session.query(Progress).filter_by(user_id=current_user.id, topic=topic).first()
        bloom_level = progress.bloom_level if progress else 1

        # Generate questions
        questions = []
        if question_type == "both":
            mcq_questions = generate_quiz(topic, bloom_level, "mcq", mcq_count)
            subj_questions = generate_quiz(topic, bloom_level, "subjective", subj_count)
            if mcq_questions and subj_questions:
                questions = mcq_questions + subj_questions
        else:
            num_q = mcq_count if question_type == "mcq" else subj_count
            questions = generate_quiz(topic, bloom_level, question_type, num_q)

        if questions:
            session['current_quiz'] = {
                'questions': questions,
                'topic': topic,
                'bloom_level': bloom_level
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
                         bloom_level=bloom_level)

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
        
        Provide:
        1. A brief overview of the topic
        2. Key concepts to understand
        3. Learning objectives
        4. Suggested study approach
        5. Common misconceptions to avoid
        
        Keep it concise but comprehensive. Format with clear sections.
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
