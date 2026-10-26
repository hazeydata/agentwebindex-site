// AWI-SIGNUP-FORM-001 progressive enhancement for form.awi-signup. Same-origin fetch only; the form works without this file
// (it posts and lands on /newsletter/thanks/<status>/). Messages are filled in by build.py from site.config.json "signup".
(function () {
  var MESSAGES = /*MESSAGES*/{};
  function valid(v) {   // mirrors signup/core.js normalizeEmail (the server decides)
    v = v.trim();
    if (!v || v.length > 254 || /\s/.test(v) || /[^\x21-\x7e]/.test(v)) return false;
    var p = v.split('@');
    return p.length === 2 && p[0].length > 0 && p[0].length <= 64 && /^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/.test(p[1]);
  }
  var forms = document.querySelectorAll('form[data-signup]');
  for (var i = 0; i < forms.length; i++) (function (form) {
    var input = form.querySelector('input[name="email"]'), out = form.querySelector('.signup-status'), btn = form.querySelector('button[type="submit"]');
    function show(st) {
      out.textContent = MESSAGES[st] || MESSAGES.error; out.setAttribute('data-status', st);
      if (st === 'invalid') { input.setAttribute('aria-invalid', 'true'); input.focus(); } else input.removeAttribute('aria-invalid');
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (btn.disabled) return;
      if (!valid(input.value)) { show('invalid'); return; }
      btn.disabled = true; btn.setAttribute('aria-busy', 'true');
      var body = {}; new FormData(form).forEach(function (v, k) { body[k] = String(v); });
      fetch(form.action, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json(); })
        .then(function (j) { show(j && MESSAGES[j.status] ? j.status : 'error'); if (j && /^(pending_confirmation|subscribed|queued)$/.test(j.status)) form.reset(); })
        .catch(function () { show('error'); })
        .then(function () { btn.disabled = false; btn.removeAttribute('aria-busy'); });
    });
  })(forms[i]);
})();
