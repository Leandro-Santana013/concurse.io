import { describe, expect, it } from 'vitest';
import { presentInternalUser, presentRankingUser } from '../../../supabase/functions/app-gateway/user-profile';

const identity = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'leandro@example.com',
  user_metadata: { full_name: 'Leandro Santana', avatar_url: 'https://example.com/avatar.png' },
};
const stored = { id: 1, email: 'private+test@users.invalid', name: null, picture: null, supabase_auth_id: identity.id };

describe('identidade real nas respostas do gateway', () => {
  it('mantém o usuário canônico e apresenta a identidade Google quando os campos antigos estão vazios', () => {
    const before = { ...stored };
    expect(presentInternalUser(stored, identity)).toEqual({
      id: 1, supabase_auth_id: identity.id, email: 'leandro@example.com',
      name: 'Leandro Santana', picture: 'https://example.com/avatar.png',
    });
    expect(stored).toEqual(before);
  });

  it('não apresenta o antigo nome técnico no lugar da identidade autenticada', () => {
    expect(presentInternalUser({ ...stored, name: 'Concurseiro Dev' }, identity).name).toBe('Leandro Santana');
  });

  it('identifica a posição própria pelo id e preserva o nome real no ranking', () => {
    const current = presentInternalUser(stored, identity);
    expect(presentRankingUser({ ...stored, name: 'Concurseiro' }, current)).toEqual({
      id: 1, name: 'Leandro Santana', picture: 'https://example.com/avatar.png',
    });
  });

  it('recupera o nome de outro participante pela conta Auth sem usar a conta atual', () => {
    const current = presentInternalUser(stored, identity);
    expect(presentRankingUser({ id: 5, name: null }, current, {
      id: '00000000-0000-0000-0000-000000000005', user_metadata: { full_name: 'Outra participante' },
    }).name).toBe('Outra participante');
  });

  it('não mostra cifrados nem e-mails pseudônimos como identidade pública', () => {
    const result = presentInternalUser({ ...stored, name: 'enc:v1:test:data' }, { id: identity.id });
    expect(result.email).toBe('');
    expect(result.name).toBe('Concurseiro');
    expect(result.id).toBe(1);
  });
});
