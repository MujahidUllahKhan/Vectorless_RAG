#!/bin/bash

# Vectorless RAG System - Setup Script
# =====================================

echo "=================================="
echo "Vectorless RAG System Setup"
echo "=================================="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p uploads
mkdir -p cache
mkdir -p backend/data
mkdir -p backend/supervised

# Setup environment file
echo ""
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  IMPORTANT: Please edit .env and add your OPENAI_API_KEY"
else
    echo "✓ .env file already exists"
fi

# Success message
echo ""
echo "=================================="
echo "✓ Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit .env and add your OpenAI API key"
echo "2. Run: python app.py"
echo "3. Open: http://localhost:5000"
echo ""
echo "For development:"
echo "  source venv/bin/activate"
echo ""
