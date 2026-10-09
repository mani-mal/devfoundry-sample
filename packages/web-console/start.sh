#!/bin/bash

# DevFoundry Web Console - Quick Start Script

set -e

echo "🚀 DevFoundry Web Console - Quick Start"
echo "========================================"

# Navigate to web-console directory
cd /home/manimal/projects/dev-foundry/packages/web-console

# Step 1: Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
  echo "📦 Installing dependencies..."
  npm install
fi

# Step 2: Create .env.local if it doesn't exist
if [ ! -f ".env.local" ]; then
  echo "📝 Creating environment file..."
  cp .env.example .env.local
fi

# Step 3: Check if API is running
echo "📡 Checking API connection..."
if ! curl -s http://localhost:3000/health > /dev/null 2>&1; then
  echo "⚠️  Warning: API at http://localhost:3000 is not responding"
  echo "   Please ensure the DevFoundry API is running."
  read -p "Continue anyway? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# Step 4: Start the development server
echo "🚀 Starting development server..."
echo "   URL: http://localhost:3001"
echo "   Default credentials: admin/devfoundry"
echo ""

npm run dev
