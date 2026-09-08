/*
 * Seletor de tema (claro/escuro) do Quati.
 * A escolha fica em localStorage ("quati-theme": "light" | "dark"); sem escolha, segue o sistema.
 * O trecho inline em skeleton/base.html aplica o atributo antes do primeiro paint para evitar o flash.
 */
(function () {
  var KEY = 'quati-theme';
  var root = document.documentElement;

  function current() {
    var stored = null;
    try { stored = localStorage.getItem(KEY); } catch (e) { /* armazenamento indisponível */ }
    if (stored === 'light' || stored === 'dark') { return stored; }
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function apply(theme) {
    root.setAttribute('data-quati-theme', theme);
    try { localStorage.setItem(KEY, theme); } catch (e) { /* ignora */ }
    var toggles = document.querySelectorAll('.q-theme-toggle');
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].setAttribute('aria-label', theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro');
      toggles[i].setAttribute('title', theme === 'dark' ? 'Tema claro' : 'Tema escuro');
    }
  }

  window.quatiTheme = {
    toggle: function () { apply(current() === 'dark' ? 'light' : 'dark'); },
    set: apply,
    current: current
  };

  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.q-theme-toggle') : null;
    if (btn) { e.preventDefault(); window.quatiTheme.toggle(); }
  });

  document.addEventListener('DOMContentLoaded', function () {
    var toggles = document.querySelectorAll('.q-theme-toggle');
    var theme = current();
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].setAttribute('title', theme === 'dark' ? 'Tema claro' : 'Tema escuro');
    }
  });
})();
