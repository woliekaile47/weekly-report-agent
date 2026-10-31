import { Component, type ReactNode } from "react";

export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error("工作空间页面加载失败", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div
        role="alert"
        className="mx-auto mt-16 max-w-2xl rounded-lg border border-rose-200 bg-white p-6"
      >
        <h1 className="text-xl font-semibold text-slate-900">
          当前页面加载失败
        </h1>
        <p className="my-3 text-sm text-slate-600">
          任务进度保存在服务端。可以重新加载，或返回任务历史打开其他任务。
        </p>
        <div className="flex flex-wrap gap-3">
          <button className="primary" onClick={() => window.location.reload()}>
            重新加载
          </button>
          <a className="secondary" href="/history">
            返回任务历史
          </a>
        </div>
      </div>
    );
  }
}
