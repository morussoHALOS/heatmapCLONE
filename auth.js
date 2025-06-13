// auth.js

async function checkPassword() {
  const input = prompt("Enter access code:");
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

  const correctHash = "5c86dc9f9cdb39dd68c5f7f112406f8ce987972afab08d5605d862bbb3609cd4";

  if (hashHex !== correctHash) {
    document.body.innerHTML = "<h2 style='color:red; text-align:center;'>Access Denied</h2>";
    throw new Error("Access denied");
  }
}

window.addEventListener('DOMContentLoaded', () => {
  setTimeout(checkPassword, 100); // slight delay improves prompt reliability
});