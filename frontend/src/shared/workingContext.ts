/**
 * Phase 9.6 work context: the classroom a staff member is working on follows them between
 * 수업·출결·성적, 성적 안내, 학생 관리 and 메시지 처리 현황 within one browser tab.
 *
 * Order: an explicit `?classroom=` link → the last classroom picked in this browser tab
 * (sessionStorage, so two tabs can work on two classes) → the first classroom. A remembered id
 * is only used when it is in the list the server returned, so it never widens access.
 */
const KEY = 'learningops.workingClassroom'

export function positiveId(value: string | null | undefined): number | undefined {
  const id = Number(value)
  return value && Number.isInteger(id) && id > 0 ? id : undefined
}

export function rememberClassroom(id: number | null | undefined) {
  try {
    if (id) sessionStorage.setItem(KEY, String(id))
  } catch { /* storage blocked: the page still works, it just starts from the first class */ }
}

export function rememberedClassroom(): number | undefined {
  try { return positiveId(sessionStorage.getItem(KEY)) } catch { return undefined }
}

export function pickClassroom(items: { id: number }[], ...preferred: (number | null | undefined)[]): number | null {
  for (const id of [...preferred, rememberedClassroom()]) {
    if (id && items.some((item) => item.id === id)) return id
  }
  return items[0]?.id ?? null
}

/** Only in-app paths are accepted as a return target (no other origin, no protocol-relative URL). */
export function safeReturnPath(value: string | null | undefined): string | null {
  return value && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\') ? value : null
}

/** `path` with `from=<return path>` added, so the target screen can offer "원래 작업으로 돌아가기". */
export function withReturn(path: string, from: string): string {
  const [pathname, search = ''] = path.split('?')
  const params = new URLSearchParams(search)
  params.set('from', from)
  return `${pathname}?${params}`
}
