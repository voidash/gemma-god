import { BrowserRouter, Route, Routes } from "react-router-dom";
import { SiteLayout } from "@/components/SiteLayout";
import { Landing } from "@/routes/Landing";
import { Chat } from "@/routes/Chat";
import { Interview } from "@/routes/Interview";
import { Admin } from "@/routes/Admin";
import { Pitch } from "@/routes/Pitch";
import { WhatsAppDemo } from "@/routes/WhatsAppDemo";
import { LiveKiosk } from "@/routes/LiveKiosk";
import { Toaster } from "@/components/ui/sonner";
import "@/lib/i18n";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <SiteLayout>
              <Landing />
            </SiteLayout>
          }
        />
        <Route
          path="/chat"
          element={
            <SiteLayout>
              <Chat />
            </SiteLayout>
          }
        />
        <Route
          path="/interview"
          element={
            <SiteLayout>
              <Interview />
            </SiteLayout>
          }
        />
        <Route
          path="/admin"
          element={
            <SiteLayout>
              <Admin />
            </SiteLayout>
          }
        />
        <Route
          path="/pitch"
          element={
            <SiteLayout>
              <Pitch />
            </SiteLayout>
          }
        />
        <Route
          path="/whatsapp"
          element={
            <SiteLayout>
              <WhatsAppDemo />
            </SiteLayout>
          }
        />
        <Route path="/kiosk" element={<LiveKiosk />} />
        <Route
          path="*"
          element={
            <SiteLayout>
              <div className="mx-auto max-w-2xl px-6 py-24 text-center">
                <h1 className="text-2xl font-semibold">404</h1>
                <p className="mt-2 text-muted-foreground">page not found</p>
              </div>
            </SiteLayout>
          }
        />
      </Routes>
      <Toaster richColors position="top-right" />
    </BrowserRouter>
  );
}
