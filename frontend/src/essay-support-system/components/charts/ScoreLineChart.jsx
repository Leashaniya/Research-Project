import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

export default function ScoreLineChart({ values = [], label = 'Sessions', yMax }) {
  const data = {
    labels: values.map((_, i) => `#${i + 1}`),
    datasets: [
      {
        label,
        data: values,
        borderColor: '#8b5cf6',
        backgroundColor: 'rgba(139,92,246,0.12)',
        tension: 0.35,
        fill: true,
        pointRadius: 4,
        pointBackgroundColor: '#8b5cf6',
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
        grid: { color: 'rgba(45,37,64,0.5)' },
      },
      y: {
        beginAtZero: true,
        max: yMax,
        ticks: { color: '#9a8cb0' },
        grid: { color: 'rgba(45,37,64,0.5)' },
      },
    },
  };

  return (
    <div style={{ height: 260 }}>
      <Line data={data} options={options} />
    </div>
  );
}
