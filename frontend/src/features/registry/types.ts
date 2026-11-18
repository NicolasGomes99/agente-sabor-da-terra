export interface Product {
  id: string
  name: string
}

export interface Producer {
  id: string
  code: string
  name: string
  cpf: string
  active: boolean
  phone: string | null
  email: string | null
  address: string | null
  municipality: string | null
  products: Product[]
}
