import { Result, Tag } from 'antd'
export function ComingSoonPage({title}:{title:string}){return <Result icon={<Tag color="processing">준비 중</Tag>} title={title} subTitle="현재 웹 전환 준비 중인 기능입니다."/>}
