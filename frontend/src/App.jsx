import { useState, useEffect } from 'react'
import './index.css'

// Replace with your actual backend URL when hosting, assuming local dev setup
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState('');
  const [balance, setBalance] = useState(0);
  const [heldBalance, setHeldBalance] = useState(0);
  const [payouts, setPayouts] = useState([]);
  
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Poll for refresh to simulate real-time
  useEffect(() => {
    fetchMerchants();
    const interval = setInterval(() => {
      if (selectedMerchantId) {
        fetchMerchants();
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [selectedMerchantId]);

  const fetchMerchants = async () => {
    try {
      const res = await fetch(`${API_URL}/merchants/`);
      if (res.ok) {
        const data = await res.json();
        setMerchants(data);
        if (data.length > 0 && !selectedMerchantId) {
          setSelectedMerchantId(data[0].id);
        }
        
        // Find current
        const current = data.find(m => m.id === (selectedMerchantId || data[0]?.id));
        if (current) {
          setBalance(current.balance);
          // Just for mockup, real system would likely expose held explicitly
          // or we can deduce it from PENDING + PROCESSING payouts
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const currentMerchantName = merchants.find(m => m.id === selectedMerchantId)?.name || 'Loading...';

  const requestPayout = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    const val = parseInt(amount, 10);
    if (isNaN(val) || val <= 0) {
      setError("Please enter a valid amount in paise.");
      setLoading(false);
      return;
    }

    try {
      // Idempotency Key is explicitly generated for THIS user action
      const idempotencyKey = crypto.randomUUID();
      
      const res = await fetch(`${API_URL}/payouts/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey
        },
        body: JSON.stringify({
          merchant: selectedMerchantId,
          amount: val
        })
      });

      const data = await res.json();
      
      if (!res.ok) {
        setError(data.error || JSON.stringify(data));
      } else {
        setSuccess('Payout requested successfully!');
        setAmount('');
        // Add to local state before next poll
        setPayouts([data, ...payouts]);
        fetchMerchants(); // Refresh balance immediately
      }
    } catch (err) {
      setError("Network or Server Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>Payout Engine Dashboard</h1>
      </header>

      <div className="dashboard-grid">
        <div className="card">
          <h2>Account Balance</h2>
          
          <div className="balance-row">
            <span className="balance-label">Merchant</span>
            <span style={{fontWeight: 600}}>{currentMerchantName}</span>
          </div>

          <div className="balance-row">
            <span className="balance-label">Available Balance</span>
            <span className="balance-value">{(balance / 100).toFixed(2)} ₹</span>
          </div>
          <div className="balance-row">
            <span className="balance-label">Held Funds (Pending/Processing)</span>
            <span className="balance-value held">Auto-deducted locally</span>
          </div>
        </div>

        <div className="card">
          <h2>Request Payout</h2>
          {error && <div className="error-msg">{error}</div>}
          {success && <div className="success-msg">{success}</div>}
          
          <form onSubmit={requestPayout}>
            <div className="form-group">
              <label>Amount (in paise, 100 paise = 1 ₹)</label>
              <input 
                type="number" 
                className="form-input" 
                value={amount}
                onChange={e => setAmount(e.target.value)}
                placeholder="e.g. 50000"
              />
            </div>
            <button type="submit" className="btn" disabled={loading}>
              {loading ? 'Processing...' : 'Withdraw Funds'}
            </button>
          </form>
        </div>
      </div>

      <div className="card payouts-section">
        <h2>Recent Payouts</h2>
        {payouts.length === 0 ? (
          <p style={{color: 'var(--text-muted)'}}>No recent payouts. Once you create a payout, it will appear here.</p>
        ) : (
          <ul className="payout-list">
            {payouts.map(p => (
              <li key={p.id} className="payout-item">
                <div className="payout-info">
                  <p><strong>Withdrawal</strong> - {(p.amount / 100).toFixed(2)} ₹</p>
                  <small>{new Date(p.created_at).toLocaleString()}</small>
                </div>
                <div className={`status-badge status-${p.status}`}>
                  {p.status}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export default App
