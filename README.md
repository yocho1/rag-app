# 🧠 Smart Document Assistant - RAG Application

A full-stack Retrieval-Augmented Generation (RAG) application that allows you to upload documents and ask questions about their content. Powered by React, FastAPI, ChromaDB, and Google Gemini AI.

![RAG Architecture](https://img.shields.io/badge/Architecture-RAG-blue)
![React](https://img.shields.io/badge/Frontend-React-61dafb)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)
![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-green)

## 🎯 Overview

This application implements a complete RAG pipeline:

1. **CHUNK** - Cut documents into manageable slices (~800 characters)
2. **EMBED** - Convert each slice into semantic vector fingerprints
3. **STORE** - Save vectors and text in ChromaDB vector database
4. **RETRIEVE** - Find relevant content using semantic search
5. **GENERATE** - Create AI-powered answers using retrieved context

## ✨ Features

- **📄 Multi-format Support**: Upload PDF, DOCX, and TXT files
- **🔍 Semantic Search**: Find relevant content using meaning, not just keywords
- **🤖 AI-Powered Answers**: Get contextual responses using Google Gemini
- **💾 Vector Database**: Efficient storage and retrieval with ChromaDB
- **🎨 Beautiful UI**: Modern, responsive interface with Tailwind CSS
- **⚡ Real-time Processing**: Instant ingestion and querying
