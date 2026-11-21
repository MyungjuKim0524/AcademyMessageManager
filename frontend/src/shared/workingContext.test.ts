import { describe, expect, it } from 'vitest'
import { pickClassroom, positiveId, rememberClassroom, safeReturnPath, withReturn } from './workingContext'

describe('working context', () => {
  const rooms = [{ id: 1 }, { id: 2 }, { id: 3 }]

  it('prefers a linked classroom, then the remembered one, then the first — only from the visible list', () => {
    expect(pickClassroom(rooms)).toBe(1)
    rememberClassroom(3)
    expect(pickClassroom(rooms)).toBe(3)
    expect(pickClassroom(rooms, 2)).toBe(2)
    expect(pickClassroom(rooms, 99)).toBe(3) // a class the user cannot see is never chosen
    expect(pickClassroom([{ id: 1 }])).toBe(1) // remembered class no longer visible
    expect(pickClassroom([])).toBeNull()
  })

  it('accepts only in-app return paths', () => {
    expect(safeReturnPath('/notifications?tab=compose')).toBe('/notifications?tab=compose')
    expect(safeReturnPath('//evil.example')).toBeNull()
    expect(safeReturnPath('/\\evil.example')).toBeNull()
    expect(safeReturnPath('https://evil.example')).toBeNull()
    expect(safeReturnPath(null)).toBeNull()
  })

  it('adds the return path to a link and parses ids strictly', () => {
    expect(withReturn('/classes?classroom=1&tab=progress', '/notifications?tab=compose&lesson=7'))
      .toBe('/classes?classroom=1&tab=progress&from=%2Fnotifications%3Ftab%3Dcompose%26lesson%3D7')
    expect(positiveId('7')).toBe(7)
    expect(positiveId('0')).toBeUndefined()
    expect(positiveId('1.5')).toBeUndefined()
    expect(positiveId(null)).toBeUndefined()
  })
})
