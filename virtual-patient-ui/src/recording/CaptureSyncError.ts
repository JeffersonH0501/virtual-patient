export class CaptureSyncError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(code);
  }
  get transient() {
    return this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500;
  }
}
