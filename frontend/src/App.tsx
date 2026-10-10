import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { createQueryClient } from "@/api/queryClient";
import { useTheme } from "@/lib/theme";
import { router } from "@/routes/router";

export function App() {
  const [client] = useState(createQueryClient);
  const [theme] = useTheme();
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster
        position="bottom-right"
        theme={theme}
        closeButton
        toastOptions={{
          className: "!rounded-xl !border-border !bg-surface !text-text !shadow-pop",
        }}
      />
    </QueryClientProvider>
  );
}
