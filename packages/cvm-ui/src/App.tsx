import type { Component } from "solid-js";
import { Router, Route } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";

import { Shell } from "./components/Shell";
import { Screeners } from "./pages/Screeners";
import { Portfolios } from "./pages/Portfolios";
import { Companies } from "./pages/Companies";
import { Compare } from "./pages/Compare";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const App: Component = () => (
  <QueryClientProvider client={client}>
    <Router root={Shell}>
      <Route path="/" component={Screeners} />
      <Route path="/screeners" component={Screeners} />
      <Route path="/screeners/:slug" component={Screeners} />
      <Route path="/portfolios" component={Portfolios} />
      <Route path="/portfolios/:slug" component={Portfolios} />
      <Route path="/companies" component={Companies} />
      <Route path="/companies/:ticker" component={Companies} />
      <Route path="/compare" component={Compare} />
      <Route path="*" component={Screeners} />
    </Router>
  </QueryClientProvider>
);

export default App;
