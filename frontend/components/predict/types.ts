export type BuyLink = { name: string; url: string };

export type Product = {
  id: string;
  name: string;
  reason: string;
  image: string; // public path e.g. /products/<id>.svg
  buy_links: BuyLink[];
};

export type Top3 = { label: string; prob: number };

export type PredictResponse = {
  top_label: string;
  top_prob: number;
  top3: Top3[];
  advice: string[];
  products: Product[];
  disclaimer: string;
  model_backend: string;
  notes: string;
  safety: string;
};

