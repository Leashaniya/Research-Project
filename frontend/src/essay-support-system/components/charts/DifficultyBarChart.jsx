import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const COLORS = {
  easy:   '#10b981',
  medium: '#f59e0b',
  hard:   '#ef4444',
};

export default function DifficultyBarChart({ difficulties = {} }) {
  const labels = Object.keys(difficulties);
  const values = Object.values(difficulties);

  const data = {
    labels,
    datasets: [
      {
        label: 'Attempts',
        data: values,
        backgroundColor: labels.map((l) => COLORS[l] || '#8b5cf6'),
        borderRadius: 6,
        maxBarThickness: 60,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1a1425',
        borderColor: '#2d2540',
        borderWidth: 1,
        titleColor: '#e8e0f0',
        bodyColor: '#e8e0f0',
      },
    },
    scales: {
      x: {
        ticks: { color: '#9a8cb0' },
        grid: { display: false },
      },
      y: {
        beginAtZero: true,
        ticks: { color: '#9a8cb0', stepSize: 1 },
        grid: { color: 'rgba(45,37,64,0.5)' },
      },
    },
  };

  return (
    <div style={{ height: 260 }}>
      <Bar data={data} options={options} />
    </div>
  );
}
