# -*- coding: utf-8 -*-
"""
简化版Flask应用
用于Vercel部署的备用方案
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
import os

app = Flask(__name__)

# 基本配置
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'my-very-strong-and-unique-secret-key-2024')

@app.route('/')
def index():
    return jsonify({
        'message': 'Interest-based Translation Platform',
        'status': 'running',
        'version': '1.0.0'
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'environment': 'vercel'
    })

@app.route('/<path:path>')
def catch_all(path):
    return jsonify({
        'message': 'Endpoint not implemented in simple mode',
        'path': path,
        'status': 'not_found'
    }), 404

if __name__ == '__main__':
    app.run(debug=False)
