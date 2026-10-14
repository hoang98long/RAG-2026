import { Component, type ReactNode } from 'react'
export default class PageBoundary extends Component<{ children: ReactNode; resetKey: string }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidUpdate(previous: { resetKey: string }) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false })
  }
  render() {
    if (this.state.failed) return <div role="alert" className="card p-6"><p className="font-semibold">Không thể hiển thị trang này.</p><p className="mt-2 text-sm text-slate-500">Bạn có thể chuyển sang trang khác hoặc tải lại ứng dụng.</p><button className="btn mt-4" onClick={() => window.location.reload()}>Tải lại trang</button></div>
    return this.props.children
  }
}
