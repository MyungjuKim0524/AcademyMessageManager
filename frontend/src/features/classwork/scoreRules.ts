export type ScoreDraft = { notTaken: boolean; score: number | null; memo: string }
type StoredScore = { result_status: string; score: number | null }

const decimals = (value: number) => (String(value).split('.')[1] ?? '').length

/** Client-side check before saving; the server validates again. A blank score is never zero. */
export function draftError<T extends StoredScore>(draft: ScoreDraft, record: T | null, maxScore: number): string | null {
  if (draft.notTaken) return null
  if (draft.score === null) return record ? '점수를 입력하거나 미응시를 선택하세요.' : null
  if (draft.score < 0) return '0 이상의 점수를 입력해주세요.'
  if (decimals(draft.score) > 2) return '소수점 둘째 자리까지 입력할 수 있습니다.'
  if (draft.score > maxScore) return `만점(${maxScore})을 넘을 수 없습니다.`
  return null
}
