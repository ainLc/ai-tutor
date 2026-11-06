import { defineStore } from 'pinia'
import { api } from '../api'

export const useCourseStore = defineStore('course', {
  state: () => ({
    courses: [],
    currentCourse: null,
    currentLesson: null,
    today: null,
    reviewQueue: [],
  }),
  actions: {
    async loadCourses() {
      this.courses = await api.listCourses()
    },
    async loadCourse(id) {
      this.currentCourse = await api.getCourse(id)
    },
    async loadLesson(id) {
      this.currentLesson = await api.getLesson(id)
    },
    async loadToday() {
      this.today = await api.today()
    },
    async loadReview() {
      const data = await api.reviewToday()
      this.reviewQueue = data.cards || []
    },
  },
})
