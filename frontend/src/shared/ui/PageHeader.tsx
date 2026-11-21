import { Typography } from 'antd'
import type { ReactNode } from 'react'

/**
 * One page header for every screen: title (h3), optional one-line description and actions on the
 * right. Replaces the mix of oversized `hero` headers and ad-hoc `Title level={2}` (Phase 9.5).
 */
export function PageHeader({ title, description, extra }: { title: ReactNode; description?: ReactNode; extra?: ReactNode }) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        <Typography.Title level={3} className="page-header-title">{title}</Typography.Title>
        {description && <Typography.Text type="secondary">{description}</Typography.Text>}
      </div>
      {extra && <div className="page-header-extra">{extra}</div>}
    </div>
  )
}
