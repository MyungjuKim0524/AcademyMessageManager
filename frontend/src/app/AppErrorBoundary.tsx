import { Alert, Button, Result } from 'antd'
import { Component, type ErrorInfo, type ReactNode } from 'react'

export class AppErrorBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false}
  static getDerivedStateFromError(){return {failed:true}}
  componentDidCatch(error:Error,info:ErrorInfo){if(import.meta.env.DEV)console.error('React rendering failed',{name:error.name,componentStack:info.componentStack})}
  render(){if(this.state.failed)return <Result status="error" title="화면을 표시할 수 없습니다." subTitle="잠시 후 다시 시도해주세요." extra={<Button onClick={()=>location.reload()}>새로고침</Button>}><Alert type="info" message="입력한 정보는 브라우저 저장소에 저장되지 않았습니다." /></Result>;return this.props.children}
}
