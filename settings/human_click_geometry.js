(el) => {
  const rects = el.getClientRects();
  const r = rects[0];
  if (!r) return null;
  let scroller = 'document';
  for (let n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
    const cs = getComputedStyle(n);
    if (/(auto|scroll|overlay)/.test(cs.overflowY + ' ' + cs.overflowX) &&
        (n.scrollHeight > n.clientHeight || n.scrollWidth > n.clientWidth)) { scroller = 'nested'; break; }
  }
  return {x: r.left, y: r.top, w: r.width, h: r.height, n: rects.length,
          bl: el.clientLeft, bt: el.clientTop, t: getComputedStyle(el).transform !== 'none',
          vw: document.documentElement.clientWidth, vh: document.documentElement.clientHeight, scroller};
}
