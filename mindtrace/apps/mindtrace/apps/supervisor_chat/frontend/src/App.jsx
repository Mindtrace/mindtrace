import ChatDialogue from './components/ChatDialogue.jsx'

export default function App() {
  return (
    <ChatDialogue
      apiUrl="/chat"
      welcomeUrl="/welcome"
      eventsUrl="/events"
      title="Service Supervisor"
    />
  )
}
