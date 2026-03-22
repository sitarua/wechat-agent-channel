const queue = [];
let running = false;

export function addTask(task) {
  queue.push(task);
  run();
}

async function run() {
  if (running) return;
  running = true;

  while (queue.length > 0) {
    const task = queue.shift();
    try {
      await task();
    } catch (e) {
      console.error("任务执行失败:", e);
    }
  }

  running = false;
}
