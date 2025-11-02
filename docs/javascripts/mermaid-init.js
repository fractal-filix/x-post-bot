// docs/javascripts/mermaid-init.js
(function () {
  function theme() {
    return document.body.getAttribute('data-md-color-scheme') === 'slate'
      ? 'dark' : 'default';
  }
  // MaterialのSPAナビゲーションに追随
  document$.subscribe(function () {
    // HTML改行 <br/> を使うので 'loose'
    mermaid.initialize({ startOnLoad: false, theme: theme(), securityLevel: 'loose' });
    mermaid.run({ querySelector: '.mermaid' });
  });
})();
