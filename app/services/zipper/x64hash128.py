# Pure Python reproduction of fingerprintjs2's x64hash128 (128-bit MurmurHash3) algorithm

def x64Add(m, n):
    m_parts = [m[0] >> 16, m[0] & 0xffff, m[1] >> 16, m[1] & 0xffff]
    n_parts = [n[0] >> 16, n[0] & 0xffff, n[1] >> 16, n[1] & 0xffff]
    o = [0, 0, 0, 0]
    
    o[3] += m_parts[3] + n_parts[3]
    o[2] += o[3] >> 16
    o[3] &= 0xffff
    
    o[2] += m_parts[2] + n_parts[2]
    o[1] += o[2] >> 16
    o[2] &= 0xffff
    
    o[1] += m_parts[1] + n_parts[1]
    o[0] += o[1] >> 16
    o[1] &= 0xffff
    
    o[0] += m_parts[0] + n_parts[0]
    o[0] &= 0xffff
    
    return [
        ((o[0] << 16) | o[1]) & 0xffffffff,
        ((o[2] << 16) | o[3]) & 0xffffffff
    ]

def x64Multiply(m, n):
    m_parts = [m[0] >> 16, m[0] & 0xffff, m[1] >> 16, m[1] & 0xffff]
    n_parts = [n[0] >> 16, n[0] & 0xffff, n[1] >> 16, n[1] & 0xffff]
    o = [0, 0, 0, 0]
    
    o[3] += m_parts[3] * n_parts[3]
    o[2] += o[3] >> 16
    o[3] &= 0xffff
    
    o[2] += m_parts[2] * n_parts[3]
    o[1] += o[2] >> 16
    o[2] &= 0xffff
    
    o[2] += m_parts[3] * n_parts[2]
    o[1] += o[2] >> 16
    o[2] &= 0xffff
    
    o[1] += m_parts[1] * n_parts[3]
    o[0] += o[1] >> 16
    o[1] &= 0xffff
    
    o[1] += m_parts[2] * n_parts[2]
    o[0] += o[1] >> 16
    o[1] &= 0xffff
    
    o[1] += m_parts[3] * n_parts[1]
    o[0] += o[1] >> 16
    o[1] &= 0xffff
    
    o[0] += (m_parts[0] * n_parts[3]) + (m_parts[1] * n_parts[2]) + (m_parts[2] * n_parts[1]) + (m_parts[3] * n_parts[0])
    o[0] &= 0xffff
    
    return [
        ((o[0] << 16) | o[1]) & 0xffffffff,
        ((o[2] << 16) | o[3]) & 0xffffffff
    ]

def x64Rotl(m, n):
    n %= 64
    if n == 32:
        return [m[1], m[0]]
    elif n < 32:
        return [
            ((m[0] << n) | (m[1] >> (32 - n))) & 0xffffffff,
            ((m[1] << n) | (m[0] >> (32 - n))) & 0xffffffff
        ]
    else:
        n -= 32
        return [
            ((m[1] << n) | (m[0] >> (32 - n))) & 0xffffffff,
            ((m[0] << n) | (m[1] >> (32 - n))) & 0xffffffff
        ]

def x64LeftShift(m, n):
    n %= 64
    if n == 0:
        return m
    elif n < 32:
        return [
            ((m[0] << n) | (m[1] >> (32 - n))) & 0xffffffff,
            (m[1] << n) & 0xffffffff
        ]
    else:
        return [
            (m[1] << (n - 32)) & 0xffffffff,
            0
        ]

def x64Xor(m, n):
    return [
        (m[0] ^ n[0]) & 0xffffffff,
        (m[1] ^ n[1]) & 0xffffffff
    ]

def x64Fmix(h):
    h = x64Xor(h, [0, h[0] >> 1])
    h = x64Multiply(h, [0xff51afd7, 0xed558ccd])
    h = x64Xor(h, [0, h[0] >> 1])
    h = x64Multiply(h, [0xc4ceb9fe, 0x1a85ec53])
    h = x64Xor(h, [0, h[0] >> 1])
    return h

def x64hash128(key: str, seed: int = 0) -> str:
    key = key or ""
    seed = seed or 0
    remainder = len(key) % 16
    bytes_len = len(key) - remainder
    h1 = [0, seed]
    h2 = [0, seed]
    k1 = [0, 0]
    k2 = [0, 0]
    c1 = [0x87c37b91, 0x114253d5]
    c2 = [0x4cf5ad43, 0x2745937f]
    
    i = 0
    while i < bytes_len:
        k1 = [
            ((ord(key[i + 4]) & 0xff)) | ((ord(key[i + 5]) & 0xff) << 8) | ((ord(key[i + 6]) & 0xff) << 16) | ((ord(key[i + 7]) & 0xff) << 24),
            ((ord(key[i]) & 0xff)) | ((ord(key[i + 1]) & 0xff) << 8) | ((ord(key[i + 2]) & 0xff) << 16) | ((ord(key[i + 3]) & 0xff) << 24)
        ]
        k2 = [
            ((ord(key[i + 12]) & 0xff)) | ((ord(key[i + 13]) & 0xff) << 8) | ((ord(key[i + 14]) & 0xff) << 16) | ((ord(key[i + 15]) & 0xff) << 24),
            ((ord(key[i + 8]) & 0xff)) | ((ord(key[i + 9]) & 0xff) << 8) | ((ord(key[i + 10]) & 0xff) << 16) | ((ord(key[i + 11]) & 0xff) << 24)
        ]
        
        k1 = x64Multiply(k1, c1)
        k1 = x64Rotl(k1, 31)
        k1 = x64Multiply(k1, c2)
        h1 = x64Xor(h1, k1)
        
        h1 = x64Rotl(h1, 27)
        h1 = x64Add(h1, h2)
        h1 = x64Add(x64Multiply(h1, [0, 5]), [0, 0x52dce729])
        
        k2 = x64Multiply(k2, c2)
        k2 = x64Rotl(k2, 33)
        k2 = x64Multiply(k2, c1)
        h2 = x64Xor(h2, k2)
        
        h2 = x64Rotl(h2, 31)
        h2 = x64Add(h2, h1)
        h2 = x64Add(x64Multiply(h2, [0, 5]), [0, 0x38495ab5])
        
        i += 16

    k1 = [0, 0]
    k2 = [0, 0]
    
    # Simulating switch-case fallthrough in Python
    if remainder >= 15:
        k2 = x64Xor(k2, x64LeftShift([0, ord(key[i + 14])], 48))
    if remainder >= 14:
        k2 = x64Xor(k2, x64LeftShift([0, ord(key[i + 13])], 40))
    if remainder >= 13:
        k2 = x64Xor(k2, x64LeftShift([0, ord(key[i + 12])], 32))
    if remainder >= 12:
        k2 = x64Xor(k2, x64LeftShift([0, ord(key[i + 11])], 24))
    if remainder >= 11:
        k2 = x64Xor(k2, x64LeftShift([0, ord(key[i + 10])], 16))
    if remainder >= 10:
        k2 = x64Xor(k2, x64LeftShift([0, ord(key[i + 9])], 8))
    if remainder >= 9:
        k2 = x64Xor(k2, [0, ord(key[i + 8])])
        k2 = x64Multiply(k2, c2)
        k2 = x64Rotl(k2, 33)
        k2 = x64Multiply(k2, c1)
        h2 = x64Xor(h2, k2)
        
    if remainder >= 8:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 7])], 56))
    if remainder >= 7:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 6])], 48))
    if remainder >= 6:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 5])], 40))
    if remainder >= 5:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 4])], 32))
    if remainder >= 4:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 3])], 24))
    if remainder >= 3:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 2])], 16))
    if remainder >= 2:
        k1 = x64Xor(k1, x64LeftShift([0, ord(key[i + 1])], 8))
    if remainder >= 1:
        k1 = x64Xor(k1, [0, ord(key[i])])
        k1 = x64Multiply(k1, c1)
        k1 = x64Rotl(k1, 31)
        k1 = x64Multiply(k1, c2)
        h1 = x64Xor(h1, k1)

    h1 = x64Xor(h1, [0, len(key)])
    h2 = x64Xor(h2, [0, len(key)])
    h1 = x64Add(h1, h2)
    h2 = x64Add(h2, h1)
    h1 = x64Fmix(h1)
    h2 = x64Fmix(h2)
    h1 = x64Add(h1, h2)
    h2 = x64Add(h2, h1)
    
    val1 = f"{(h1[0] & 0xffffffff):08x}"
    val2 = f"{(h1[1] & 0xffffffff):08x}"
    val3 = f"{(h2[0] & 0xffffffff):08x}"
    val4 = f"{(h2[1] & 0xffffffff):08x}"
    
    return val1 + val2 + val3 + val4
