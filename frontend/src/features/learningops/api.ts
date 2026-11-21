import { ApiClientError } from '../../shared/api/ApiClientError'
import { apiClient } from '../../shared/api/client'

export interface Classroom { id:number; name:string; class_type:string; is_active:boolean }
export interface Student { id:number; name:string; school_name:string|null }
// parent_* are only present for administrators.
export interface ClassroomStudent extends Student { enrollment_id:number; enrollment_status:string; enrolled_at:string; parent_name?:string|null; parent_email?:string|null }
export interface EnrollmentPause { id:number; enrollment_id:number; paused_from:string; resumed_on:string|null; source:'MANUAL'|'STATUS_CHANGE'; created_at:string }
export const pauses=async(classroomId:number,enrollmentId:number)=>(await apiClient.get<{enrollment_status:string;items:EnrollmentPause[]}>(`/api/classrooms/${classroomId}/enrollments/${enrollmentId}/pauses`)).data
export const pause=async(classroomId:number,enrollmentId:number,paused_from:string)=>(await apiClient.post<EnrollmentPause>(`/api/classrooms/${classroomId}/enrollments/${enrollmentId}/pauses`,{paused_from})).data
export const resume=async(classroomId:number,enrollmentId:number,pauseId:number,resumed_on:string)=>(await apiClient.post<EnrollmentPause>(`/api/classrooms/${classroomId}/enrollments/${enrollmentId}/pauses/${pauseId}/resume`,{resumed_on})).data
export interface StudentContact { id:number; name:string; parent_name:string|null; parent_email:string|null }
export const studentContact=async(studentId:number)=>(await apiClient.get<StudentContact>(`/api/students/${studentId}/contact`)).data
export const updateStudentContact=async(studentId:number,parent_name:string|null,parent_email:string|null)=>(await apiClient.patch<StudentContact>(`/api/students/${studentId}/contact`,{parent_name,parent_email})).data
export const createClassroom=async(name:string,class_type:string)=>(await apiClient.post<Classroom>('/api/classrooms',{name,class_type})).data
/** 반 관리: rename, or end (is_active=false) / resume operation. Records are always kept. */
export const updateClassroom=async(id:number,change:{name?:string;is_active?:boolean})=>(await apiClient.patch<Classroom>(`/api/classrooms/${id}`,change)).data
/** Deletes a class with no records only (409 CLASSROOM_HAS_RECORDS otherwise: use 운영 종료). */
export const deleteClassroom=async(id:number)=>{await apiClient.delete(`/api/classrooms/${id}`)}
/** Registers a student; with `enrollment` the student is enrolled in that class in the same save. */
export const createStudent=async(name:string,school_name:string,parent_email?:string,enrollment?:{classroom_id:number;enrolled_at:string})=>(await apiClient.post<Student>('/api/students',{name,school_name:school_name||null,parent_email:parent_email?.trim()||null,...enrollment})).data
export const enroll=async(classroomId:number,studentId:number,enrolled_at:string)=>(await apiClient.post(`/api/classrooms/${classroomId}/enrollments`,{student_id:studentId,enrolled_at})).data
/** Classes in operation (assigned ones for non-administrators); `includeInactive` adds ended classes (administrators). */
export const classrooms=async(includeInactive=false)=>(await apiClient.get<{items:Classroom[]}>('/api/classrooms',{params:{limit:100,...(includeInactive?{include_inactive:true}:{})}})).data.items
// All students (administrators only), with every class each one is enrolled in.
export interface StudentEnrollmentSummary { enrollment_id:number; classroom_id:number; classroom_name:string; status:string; enrolled_at:string; classroom_active?:boolean }
export interface StudentListItem extends Student { parent_name:string|null; parent_email:string|null; enrollments:StudentEnrollmentSummary[] }
export interface StudentPage { items:StudentListItem[]; total:number; limit:number; offset:number }
export const allStudents=async(q?:string,limit=50,offset=0)=>(await apiClient.get<StudentPage>('/api/students',{params:{q:q?.trim()||undefined,limit,offset}})).data
/** Page size of the class student list (the API's maximum; its default is 50). */
export const STUDENT_PAGE_SIZE=100
const MAX_STUDENT_PAGES=100 // safety stop: 10,000 students per class
/**
 * Every student of a class. The endpoint pages with limit/offset, has no total and orders by
 * student id (one enrolment per student and class), so pages are read until a short one comes
 * back. Before Phase 10.5 only the first 50 were requested and the rest silently disappeared.
 * A failing page rejects the whole call (never a silently partial list); a row repeated across
 * pages (an enrolment added while paging) is kept once.
 */
export const students=async(classroomId:number)=>{
  const rows:ClassroomStudent[]=[]
  const seen=new Set<number>()
  for(let page=0;page<MAX_STUDENT_PAGES;page+=1){
    const items=(await apiClient.get<{items:ClassroomStudent[]}>(`/api/classrooms/${classroomId}/students`,{params:{limit:STUDENT_PAGE_SIZE,offset:page*STUDENT_PAGE_SIZE}})).data.items
    for(const row of items){if(!seen.has(row.enrollment_id)){seen.add(row.enrollment_id);rows.push(row)}}
    if(items.length<STUDENT_PAGE_SIZE)return rows
  }
  throw new ApiClientError('학생 목록이 너무 많아 모두 불러오지 못했습니다.', 'STUDENT_LIST_TOO_LONG')
}
