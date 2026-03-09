import { initializeApp } from "https://www.gstatic.com/firebasejs/10.9.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, createUserWithEmailAndPassword, GoogleAuthProvider, signInWithPopup, updateProfile }
    from "https://www.gstatic.com/firebasejs/10.9.0/firebase-auth.js";

const firebaseConfig = {
    apiKey: "AIzaSyBNhLEfyfz_JclCVWm7ns1m4ty_MYuqY9Y",
    authDomain: "autojobagent-dev-99.firebaseapp.com",
    projectId: "autojobagent-dev-99",
    storageBucket: "autojobagent-dev-99.firebasestorage.app",
    messagingSenderId: "534327618263",
    appId: "1:534327618263:web:e2e97443fcc9b4129cde92"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

async function sendTokenToBackend(idToken) {
    try {
        const response = await fetch('/auth/firebase-login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ idToken })
        });
        const data = await response.json();
        if (data.success) {
            window.location.href = data.redirect;
        } else {
            showError(data.message || data.error || 'Authentication failed on server');
        }
    } catch (e) {
        showError('Network error connecting to backend');
    }
}

function showError(msg) {
    let flashContainer = document.getElementById('flash-container');
    if (!flashContainer) {
        const card = document.querySelector('.auth-card');
        const subtitle = document.querySelector('.auth-subtitle');
        flashContainer = document.createElement('div');
        flashContainer.id = 'flash-container';
        subtitle.after(flashContainer);
    }
    flashContainer.innerHTML = `<div class="flash flash-error">${msg}</div>`;
}

// Make accessible to non-module scripts
window.firebaseAuth = auth;
window.googleProvider = googleProvider;
window.signInWithPopup = signInWithPopup;
window.signInWithEmailAndPassword = signInWithEmailAndPassword;
window.createUserWithEmailAndPassword = createUserWithEmailAndPassword;
window.updateProfile = updateProfile;
window.sendTokenToBackend = sendTokenToBackend;
window.showError = showError;
