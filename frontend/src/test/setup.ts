import '@testing-library/jest-dom/vitest'

// jsdom does not implement native dialog methods. Real focus/inert behavior is
// covered by browser tests rather than simulated by this API shim.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
}
