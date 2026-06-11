class StptMapPanel extends HTMLElement {
  connectedCallback() {
    if (this._iframe) return;
    this._iframe = document.createElement("iframe");
    this._iframe.src = "https://live.stpt.ro/";
    this._iframe.style.width = "100%";
    this._iframe.style.height = "100%";
    this._iframe.style.border = "0";
    this.appendChild(this._iframe);
  }
}

customElements.define("stpt-map-panel", StptMapPanel);
