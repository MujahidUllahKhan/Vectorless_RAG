# Quick Start Guide

Get up and running with Vectorless RAG in 5 minutes!

## Prerequisites

- Python 3.8 or higher
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))
- Git (for cloning the repository)

## Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/vectorless-rag-system.git
cd vectorless-rag-system
```

## Step 2: Run Setup Script

### On Linux/Mac:
```bash
bash setup.sh
```

### On Windows:
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Step 3: Configure API Key

Edit `.env` file and add your OpenAI API key:

```bash
OPENAI_API_KEY=sk-your-actual-api-key-here
```

## Step 4: Start the Server

```bash
python app.py
```

You should see:
```
VECTORLESS RAG API SERVER
========================
✅ OpenAI API key configured
Server starting on http://localhost:5000
```

## Step 5: Open the Web Interface

Open your browser and go to:
```
http://localhost:5000
```

## Step 6: Upload and Chat!

1. Click "📁 Choose PDF Files"
2. Select one or more PDF documents
3. Wait for indexing to complete (you'll see "✓ Ready")
4. Type your question in the chat box
5. See the answer with full citations and retrieval steps!

## Troubleshooting

### "OPENAI_API_KEY not set" error
- Make sure you edited `.env` file
- Restart the server after editing `.env`

### "No module named 'flask'" error
- Activate virtual environment: `source venv/bin/activate` (Mac/Linux) or `venv\Scripts\activate` (Windows)
- Run: `pip install -r requirements.txt`

### Port 5000 already in use
- Edit `.env` and change `PORT=5000` to another port like `PORT=8000`
- Or stop the process using port 5000

### PDF indexing fails
- Check your OpenAI API key is valid
- Ensure PDF is not password protected
- Try a smaller PDF first (< 20 pages)

## Next Steps

- **Tutorial**: Check out `backend/notebooks/tutorial.ipynb` for detailed explanations
- **Documentation**: See `backend/docs/complete_guide.tex` for theoretical background
- **API**: Read `docs/API.md` for REST API documentation
- **Examples**: Try the example QA dataset in `backend/supervised/example_qa_dataset.json`

## Need Help?

- Check the [FAQ](docs/FAQ.md)
- Open an issue on GitHub
- Read the full [README](README.md)

## Tips

- Start with smaller PDFs (< 50 pages) for faster indexing
- Documents with a Table of Contents work best
- Use specific questions for better results
- Check the "Retrieval Process" section to understand how answers are found

Happy chatting! 🚀
