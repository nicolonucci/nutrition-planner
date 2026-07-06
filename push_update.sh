#!/bin/bash
cd "/Users/nicolo/Documents/Claude/Projects/Nutrition and Training"
rm -f .git/index.lock .git/refs/remotes/origin/main.lock 2>/dev/null
git config user.email "nicolonuk.social@gmail.com"
git config user.name "Nicolò Nucci"
git add ricettario.html
git commit -m "Fix: rimuovi pallini radio visibili nella sezione Riposo"
git push origin main
echo "✅ Done!"
rm -- "$0"
