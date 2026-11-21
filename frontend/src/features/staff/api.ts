import { apiClient } from '../../shared/api/client'

export type StaffRole = 'ADMIN' | 'TEACHER' | 'ASSISTANT'
export type StaffStatus = 'ACTIVE' | 'INACTIVE'
export type AssignableRole = 'TEACHER' | 'ASSISTANT'
export interface Staff { id:number; email:string; display_name:string|null; role:StaffRole; status:StaffStatus; created_at:string; updated_at:string }
export interface Classroom { id:number; name:string; class_type:string; is_active:boolean }
export interface Assignment { id:number; classroom_id:number; classroom_name:string; staff_user_id:number; assignment_role:AssignableRole; valid_from:string; valid_to:string|null }
export interface ClassroomStaff { id:number; classroom_id:number; staff_user_id:number; assignment_role:AssignableRole; valid_from:string; valid_to:string|null; email:string; display_name:string|null; staff_status:StaffStatus }

export const staffLabel=(staff:{display_name:string|null;email:string})=>staff.display_name||staff.email

export const listStaff=async()=>(await apiClient.get<{items:Staff[]}>('/api/staff',{params:{limit:100}})).data.items
export const createStaff=async(displayName:string,email:string,password:string,role:AssignableRole)=>(await apiClient.post<Staff>('/api/staff',{display_name:displayName,email,password,role})).data
export const updateStaffName=async(staffId:number,displayName:string)=>(await apiClient.patch<Staff>(`/api/staff/${staffId}`,{display_name:displayName})).data
export const updateStaffStatus=async(staffId:number,status:StaffStatus)=>(await apiClient.patch<Staff>(`/api/staff/${staffId}/status`,{status})).data
/** HARD = removed (no work history); SOFT = cannot log in and hidden, its name stays on past records. */
export const deleteStaff=async(staffId:number)=>(await apiClient.delete<{staff_id:number;mode:'HARD'|'SOFT'}>(`/api/staff/${staffId}`)).data
/** SEC-10-B: one-time password reset code (shown once; hand it over in person, valid 15 min). */
export const issueResetCode=async(staffId:number)=>(await apiClient.post<{staff_id:number;code:string;expires_at:string}>(`/api/staff/${staffId}/password-reset-code`)).data
export const listClassrooms=async()=>(await apiClient.get<{items:Classroom[]}>('/api/classrooms',{params:{limit:100}})).data.items
export const listAssignments=async(staffId:number)=>(await apiClient.get<{items:Assignment[]}>(`/api/staff/${staffId}/assignments`)).data.items
export const listClassroomStaff=async(classroomId:number)=>(await apiClient.get<{items:ClassroomStaff[]}>(`/api/classrooms/${classroomId}/staff`,{params:{limit:100}})).data.items
export const createAssignment=async(classroomId:number,staffId:number,assignmentRole:AssignableRole,validFrom:string)=>(await apiClient.post(`/api/classrooms/${classroomId}/assignments`,{staff_user_id:staffId,assignment_role:assignmentRole,valid_from:validFrom})).data
export const removeAssignment=async(classroomId:number,assignmentId:number)=>apiClient.delete(`/api/classrooms/${classroomId}/assignments/${assignmentId}`)
