const DB_NAME = 'ai-tutor-offline'
const DB_VER = 1

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VER)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains('queue')) db.createObjectStore('queue')
      if (!db.objectStoreNames.contains('pending')) db.createObjectStore('pending', { keyPath: 'id' })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function saveReviewQueue(cards) {
  const db = await openDb()
  await new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite')
    tx.objectStore('queue').put({ cards, savedAt: Date.now() }, 'today')
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function loadReviewQueue() {
  const db = await openDb()
  const data = await new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readonly')
    const req = tx.objectStore('queue').get('today')
    req.onsuccess = () => resolve(req.result || null)
    req.onerror = () => reject(req.error)
  })
  db.close()
  if (Array.isArray(data)) return { cards: data }
  return data
}

export async function enqueueRating(cardId, rating) {
  const db = await openDb()
  await new Promise((resolve, reject) => {
    const tx = db.transaction('pending', 'readwrite')
    tx.objectStore('pending').put({ id: `${cardId}-${Date.now()}`, cardId, rating, at: Date.now() })
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function flushPending(reviewFn) {
  const db = await openDb()
  const items = await new Promise((resolve, reject) => {
    const tx = db.transaction('pending', 'readonly')
    const req = tx.objectStore('pending').getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
  for (const item of items) {
    try {
      await reviewFn(item.cardId, item.rating)
      await new Promise((resolve, reject) => {
        const tx = db.transaction('pending', 'readwrite')
        tx.objectStore('pending').delete(item.id)
        tx.oncomplete = resolve
        tx.onerror = () => reject(tx.error)
      })
    } catch (e) {
      break
    }
  }
  db.close()
}
