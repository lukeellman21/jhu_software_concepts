from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    return render_template('home.html', active_page='home')

@main_bp.route('/projects')
def projects():
    return render_template('projects.html', active_page='projects')

@main_bp.route('/contact')
def contact():
    return render_template('contact.html', active_page='contact')
