export default function HomePage() {
  return (
    <main style={{ padding: "3rem 2rem", maxWidth: 720, margin: "0 auto" }}>
      <h1>AgentStack</h1>
      <p>
        Frontend scaffold. The chat UI, document uploader, and eval dashboard land
        in Week 4. Backend is at <code>http://localhost:8000/docs</code>.
      </p>
      <ul>
        <li>
          <a href="/voice">Voice agent (Week 4)</a> — talk to your collection
        </li>
        <li>
          <a href="http://localhost:8000/docs">API (Swagger)</a>
        </li>
        <li>
          <a href="http://localhost:6333/dashboard">Qdrant dashboard</a>
        </li>
        <li>
          <a href="http://localhost:6006">Phoenix traces</a>
        </li>
        <li>
          <a href="http://localhost:3001">Grafana</a>
        </li>
      </ul>
    </main>
  );
}
