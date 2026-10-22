# Project navigation

Read `architecture/system.c4`, then `architecture/modules.c4` and `docs/decisions.md` before structural changes. Verify against current source.

- This is a vanilla HTML/CSS/JavaScript prototype. No backend, real payments, account system or real inventory exists.
- `src/domain.js` owns booking rules; `src/data.js` owns demo catalog; `src/storage.js` owns persistence; `src/map.js` owns geographic map; `src/app.js` owns UI orchestration.
- Keep demo claims explicit. Never represent fictional prices, approximate locations or illustrative photos as verified property data.
- Every structural change must update the architecture in the same change. Run `npm run arch:sync` for real import dependencies; edit `architecture/system.c4` when responsibilities or external services change. Do not claim this detects arbitrary semantic drift.
- Run `npm test`, `npm run build`, and `npm run arch:check`. Verify affected flows in a browser, including 390px and desktop layouts.
- Never store real credentials or payment details in client code or localStorage.
- Do not add a framework or backend without user direction.
