# Сцена без страха — independent frontend

## Deployment

The `public/` folder is an ordinary static website. It contains no ChatGPT SDK, platform login or hosting-specific runtime code. Serve this directory on your own HTTPS hosting/domain; no build step is required. HTTPS is required for microphone and camera access.

For local use: `python -m http.server 8080 --directory public`, then open http://localhost:8080.

Entrypoint: public/index.html. Relative assets work under a subdirectory. No SPA route rewrites are required.

## Current product

Guest access is implemented. Devices, recording, playback and download work in compatible browsers. Questions and result text are explicitly demonstrative. History is stored in the browser, and recordings are in memory until the tab reloads or closes. No recordings are sent to a server.

## Email/password accounts — backend work required

Real account authentication is not included in this frontend. Do not implement passwords or simulated login with localStorage. Coordinate authentication with the existing backend developer, preserving an anonymous guest option.

Proposed UI: Sign in → email + password; Register → email + password + confirmation; Forgot password → email. Main training flow stays accessible through “Continue as guest”. Signed-in users should see their own server-backed history. Guest users see browser-local history.

Backend needs registration, sign-in, sign-out, current session, verification/reset flows and per-user attempt ownership. Suggested API operations (final paths and formats must be agreed with the backend developer): POST /auth/register, POST /auth/login, POST /auth/logout, GET /auth/me, POST /auth/password-reset/request, POST /auth/password-reset/confirm. Use server-managed sessions and appropriate cookie/CSRF protections, password hashing and login abuse protection. Email verification/reset needs a configured mail service.

A two-step registration interface is now included: email/name/password, then role selection. The auth adapter deliberately rejects until a real backend is connected; no account or session is simulated. Existing-account login is not included. No real authentication is claimed. See FRONTEND_README.md for the adapter contract.

## AI integration

Replace public/api.js with the actual backend adapter. Existing interfaces and result/recording schemas are documented in FRONTEND_README.md. Keep AI credentials on the server. If frontend and backend use different origins, configure CORS and cookie/session rules deliberately; hosting both behind the same domain simplifies integration.

## Outstanding release checks

Test physical camera/microphone, permission refusal, audio-only capture, recording download and mobile browsers on the final HTTPS domain. Automated state tests use fake media devices, not hardware.
