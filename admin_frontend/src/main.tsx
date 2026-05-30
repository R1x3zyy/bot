import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Boxes,
  BarChart3,
  Check,
  ClipboardList,
  Database,
  Link as LinkIcon,
  LogOut,
  Moon,
  Package,
  RefreshCw,
  Save,
  Settings,
  Sun,
  Trash2,
  Users,
} from 'lucide-react';
import './styles.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

type Stats = {
  users: number;
  orders: number;
  links: number;
};

type VisitPoint = {
  visit_date: string;
  visits: number;
};

type Order = {
  id: number;
  user_id: number;
  username: string;
  product_title: string;
  price_rub: number;
  contact: string;
  status: string;
  created_at: string;
};

type StoreUser = {
  id: number;
  username: string;
  first_name: string;
  balance: number;
  language: string;
  ref_code: string;
  created_at: string;
};

type StoreLink = {
  id: number;
  url: string;
  is_issued: boolean;
  issued_to: number | null;
  created_at: string;
};

type Product = {
  code: string;
  title: string;
  price_rub: number;
  price_usd: number;
  description: string;
};

type Tab = 'orders' | 'links' | 'product' | 'users';

const ORDER_STATUSES = [
  'Ожидает обработки',
  'Оплачен',
  'Оплачен Crypto Bot, ожидает обработки',
  'Выдан',
  'Выдан автоматически',
  'Резерв, нет в наличии',
  'Отменен',
];

function authHeader(login: string, password: string) {
  return `Basic ${btoa(`${login}:${password}`)}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatChartDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(value));
}

function App() {
  const [login, setLogin] = useState(localStorage.getItem('admin_login') || 'admin');
  const [password, setPassword] = useState(localStorage.getItem('admin_password') || '');
  const [isAuthed, setIsAuthed] = useState(Boolean(localStorage.getItem('admin_password')));
  const [theme, setTheme] = useState(localStorage.getItem('admin_theme') || 'light');
  const [tab, setTab] = useState<Tab>('orders');
  const [stats, setStats] = useState<Stats>({ users: 0, orders: 0, links: 0 });
  const [visits, setVisits] = useState<VisitPoint[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [users, setUsers] = useState<StoreUser[]>([]);
  const [links, setLinks] = useState<StoreLink[]>([]);
  const [product, setProduct] = useState<Product | null>(null);
  const [newLinks, setNewLinks] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const headers = useMemo(
    () => ({
      Authorization: authHeader(login, password),
      'Content-Type': 'application/json',
    }),
    [login, password],
  );

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { ...headers, ...(options.headers || {}) },
    });

    if (!response.ok) {
      throw new Error(response.status === 401 ? 'Неверный логин или пароль' : 'Ошибка запроса');
    }

    return response.json();
  }

  async function loadAll() {
    setLoading(true);
    setMessage('');
    try {
      const [nextStats, nextVisits, nextOrders, nextUsers, nextLinks, nextProduct] = await Promise.all([
        request<Stats>('/api/stats'),
        request<VisitPoint[]>('/api/visits?days=14'),
        request<Order[]>('/api/orders'),
        request<StoreUser[]>('/api/users'),
        request<StoreLink[]>('/api/links'),
        request<Product>('/api/product'),
      ]);
      setStats(nextStats);
      setVisits(nextVisits);
      setOrders(nextOrders);
      setUsers(nextUsers);
      setLinks(nextLinks);
      setProduct(nextProduct);
      localStorage.setItem('admin_login', login);
      localStorage.setItem('admin_password', password);
      setIsAuthed(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить данные');
      setIsAuthed(false);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isAuthed) {
      loadAll();
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('admin_theme', theme);
  }, [theme]);

  async function submitLogin(event: React.FormEvent) {
    event.preventDefault();
    await loadAll();
  }

  async function addLinkBatch(event: React.FormEvent) {
    event.preventDefault();
    const result = await request<{ added: number }>('/api/links', {
      method: 'POST',
      body: JSON.stringify({ links: newLinks }),
    });
    setNewLinks('');
    setMessage(`Добавлено ссылок: ${result.added}`);
    await loadAll();
  }

  async function saveProduct(event: React.FormEvent) {
    event.preventDefault();
    if (!product) return;
    const saved = await request<Product>('/api/product', {
      method: 'PUT',
      body: JSON.stringify(product),
    });
    setProduct(saved);
    setMessage('Данные товара сохранены');
    await loadAll();
  }

  async function updateStatus(orderId: number, status: string) {
    await request<Order>(`/api/orders/${orderId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    await loadAll();
  }

  async function deleteLink(linkId: number) {
    if (!window.confirm('Удалить эту ссылку?')) return;
    await request<{ deleted: number }>(`/api/links/${linkId}`, {
      method: 'DELETE',
    });
    setMessage('Ссылка удалена');
    await loadAll();
  }

  async function clearAvailableLinks() {
    if (!window.confirm('Удалить все ссылки, которые еще не выданы?')) return;
    const result = await request<{ deleted: number }>('/api/links/available', {
      method: 'DELETE',
    });
    setMessage(`Удалено невыданных ссылок: ${result.deleted}`);
    await loadAll();
  }

  function logout() {
    localStorage.removeItem('admin_password');
    setPassword('');
    setIsAuthed(false);
  }

  function toggleTheme() {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }

  const maxVisits = Math.max(...visits.map((point) => point.visits), 1);

  if (!isAuthed) {
    return (
      <main className="login-screen">
        <form className="login-panel" onSubmit={submitLogin}>
          <Database size={32} />
          <h1>Админка магазина</h1>
          <label>
            Логин
            <input value={login} onChange={(event) => setLogin(event.target.value)} />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button type="submit" disabled={loading}>
            <Check size={18} />
            Войти
          </button>
          {message && <p className="message error">{message}</p>}
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Gemini Store</h1>
          <p>Управление товаром, ссылками и заказами</p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="ghost"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить темную тему'}
            title={theme === 'dark' ? 'Светлая тема' : 'Темная тема'}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button type="button" className="ghost" onClick={loadAll} disabled={loading}>
            <RefreshCw size={18} />
          </button>
          <button type="button" className="ghost" onClick={logout}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <section className="stats-grid">
        <div className="stat">
          <Users size={20} />
          <span>Пользователи</span>
          <strong>{stats.users}</strong>
        </div>
        <div className="stat">
          <ClipboardList size={20} />
          <span>Заказы</span>
          <strong>{stats.orders}</strong>
        </div>
        <div className="stat">
          <Boxes size={20} />
          <span>Ссылки</span>
          <strong>{stats.links}</strong>
        </div>
      </section>

      <section className="panel visits-panel">
        <div className="panel-heading">
          <h2>
            <BarChart3 size={20} />
            Уникальные посещения
          </h2>
          <span className="muted-label">за 14 дней</span>
        </div>
        <div className="visits-chart" aria-label="График уникальных посещений бота по дням">
          {visits.map((point) => (
            <div className="visit-bar" key={point.visit_date}>
              <strong>{point.visits}</strong>
              <div className="bar-track">
                <span style={{ height: `${Math.max((point.visits / maxVisits) * 100, point.visits ? 8 : 0)}%` }} />
              </div>
              <small>{formatChartDate(point.visit_date)}</small>
            </div>
          ))}
        </div>
      </section>

      <nav className="tabs">
        <button className={tab === 'orders' ? 'active' : ''} onClick={() => setTab('orders')}>
          <ClipboardList size={18} />
          Заказы
        </button>
        <button className={tab === 'links' ? 'active' : ''} onClick={() => setTab('links')}>
          <LinkIcon size={18} />
          Ссылки
        </button>
        <button className={tab === 'product' ? 'active' : ''} onClick={() => setTab('product')}>
          <Settings size={18} />
          Товар
        </button>
        <button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}>
          <Users size={18} />
          Пользователи
        </button>
      </nav>

      {message && <p className="message">{message}</p>}

      {tab === 'orders' && (
        <section className="panel">
          <h2>Заказы</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Товар</th>
                  <th>Пользователь</th>
                  <th>Контакт</th>
                  <th>Статус</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td>#{order.id}</td>
                    <td>{order.product_title}</td>
                    <td>
                      {order.username}
                      <small>{order.user_id}</small>
                    </td>
                    <td>{order.contact}</td>
                    <td>
                      <select
                        value={order.status}
                        onChange={(event) => updateStatus(order.id, event.target.value)}
                      >
                        {!ORDER_STATUSES.includes(order.status) && <option>{order.status}</option>}
                        {ORDER_STATUSES.map((status) => (
                          <option key={status}>{status}</option>
                        ))}
                      </select>
                    </td>
                    <td>{formatDate(order.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === 'links' && (
        <section className="split">
          <form className="panel" onSubmit={addLinkBatch}>
            <h2>Добавить ссылки</h2>
            <label>
              Каждая ссылка с новой строки
              <textarea
                value={newLinks}
                onChange={(event) => setNewLinks(event.target.value)}
                placeholder="https://example.com/link-1&#10;https://example.com/link-2"
              />
            </label>
            <button type="submit">
              <Package size={18} />
              Добавить
            </button>
          </form>
          <section className="panel">
            <div className="panel-heading">
              <h2>Последние ссылки</h2>
              <button className="danger" type="button" onClick={clearAvailableLinks}>
                <Trash2 size={18} />
                Очистить невыданные
              </button>
            </div>
            <div className="link-list">
              {links.map((link) => (
                <div className="link-row" key={link.id}>
                  <span>{link.url}</span>
                  <strong>{link.is_issued ? 'Выдана' : 'В наличии'}</strong>
                  <button
                    className="danger icon-button"
                    type="button"
                    aria-label="Удалить ссылку"
                    title="Удалить ссылку"
                    onClick={() => deleteLink(link.id)}
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
            </div>
          </section>
        </section>
      )}

      {tab === 'product' && product && (
        <form className="panel product-form" onSubmit={saveProduct}>
          <h2>Настройки товара</h2>
          <div className="product-row">
            <label>
              Название
              <input
                value={product.title}
                onChange={(event) => setProduct({ ...product, title: event.target.value })}
              />
            </label>
            <label>
              Цена ₽
              <input
                type="number"
                min="0"
                step="1"
                value={product.price_rub}
                onChange={(event) => setProduct({ ...product, price_rub: Number(event.target.value) })}
              />
            </label>
            <label>
              Цена $
              <input
                type="number"
                min="0"
                step="0.01"
                value={product.price_usd}
                onChange={(event) => setProduct({ ...product, price_usd: Number(event.target.value) })}
              />
            </label>
          </div>
          <label>
            Описание в карточке товара
            <textarea
              value={product.description}
              onChange={(event) => setProduct({ ...product, description: event.target.value })}
            />
          </label>
          <button type="submit">
            <Save size={18} />
            Сохранить
          </button>
        </form>
      )}

      {tab === 'users' && (
        <section className="panel">
          <h2>Пользователи</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Username</th>
                  <th>Имя</th>
                  <th>Баланс</th>
                  <th>Реф. код</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.id}</td>
                    <td>{user.username || '-'}</td>
                    <td>{user.first_name || '-'}</td>
                    <td>{Number(user.balance).toFixed(0)} ₽</td>
                    <td>{user.ref_code}</td>
                    <td>{formatDate(user.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
