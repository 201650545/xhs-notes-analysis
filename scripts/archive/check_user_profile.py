import urllib.request, json, time

API = 'http://127.0.0.1:10086/command'

def call(action, args=None, session='xhs'):
    payload = {'action': action, 'session': session}
    if args is not None:
        payload['args'] = args
    req = urllib.request.Request(API, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

call('navigate', {'url': 'https://www.xiaohongshu.com/user/profile/6292cc04000000002102272a'})
time.sleep(5)

check_code = """
(() => {
  const cards = document.querySelectorAll('section.note-item, div.note-item');
  const items = [];
  cards.forEach(c => {
    const a = c.querySelector('a.cover') || c.querySelector('a');
    const href = a ? (a.getAttribute('href') || '') : '';
    const title = (c.querySelector('.title, a.title')?.innerText || '').trim();
    const like = (c.querySelector('.like-wrapper .count, .count, .like')?.innerText || '').trim();
    items.push({ href, title, like });
  });
  const tabs = [...document.querySelectorAll('.reds-tab-item, [class*="tab"]')].map(t => (t.innerText || '').trim());
  return JSON.stringify({
    title: document.title,
    tabs: tabs.filter(Boolean).slice(0, 10),
    cardCount: cards.length,
    items: items
  });
})()
"""

res = call('evaluate', {'code': check_code})
print('User Profile Info:', res.get('data', {}).get('value'))
