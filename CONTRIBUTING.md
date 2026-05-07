# Contributing to Vectorless RAG System

Thank you for considering contributing to the Vectorless RAG System! This document provides guidelines for contributions.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- System information (OS, Python version)
- Error messages or logs

### Suggesting Features

Feature requests are welcome! Please include:
- Clear description of the feature
- Use case and motivation
- Proposed implementation (if you have ideas)

### Code Contributions

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes**
4. **Test thoroughly**
5. **Commit with clear messages**: `git commit -m 'Add amazing feature'`
6. **Push to your fork**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/vectorless-rag-system.git
cd vectorless-rag-system

# Run setup script
bash setup.sh

# Activate virtual environment
source venv/bin/activate

# Start development server
python app.py
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable names
- Add docstrings to functions and classes
- Comment complex logic
- Keep functions focused and small

## Testing

Before submitting a PR:
- Test the core RAG functionality
- Test API endpoints
- Test frontend interactions
- Verify documentation changes

## Areas for Contribution

### High Priority
- [ ] Multi-document querying implementation
- [ ] Hybrid vector + tree retrieval
- [ ] Advanced visualization dashboard
- [ ] Performance optimizations

### Medium Priority
- [ ] Support for more document formats (DOCX, HTML)
- [ ] Custom LLM support (Ollama, local models)
- [ ] Export functionality (PDF reports)
- [ ] Mobile-responsive improvements

### Documentation
- [ ] Video tutorials
- [ ] More usage examples
- [ ] API documentation improvements
- [ ] Deployment guides (AWS, Azure, GCP)

## Questions?

Feel free to open an issue with the "question" label.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
